#requires -Version 5.1
<#
.SYNOPSIS
Temporarily simulate the website side of an actual Wizard CLI /login request.
.DESCRIPTION
Uses existing session/CSRF endpoints only. Never accepts the CLI verifier,
exchanges a code, obtains an account bearer, or saves website cookies to disk.
Local HTTP requires -LocalDevelopment or WIZARD_ACCOUNT_LOCAL_DEV=1.
#>
[CmdletBinding()]
param(
    [string]$ServiceOrigin = $(if ($env:WIZARD_ACCOUNT_URL) { $env:WIZARD_ACCOUNT_URL } else { 'http://localhost:8090' }),
    [switch]$LocalDevelopment,
    [ValidateRange(1, 30)][int]$TimeoutSeconds = 8,
    [ValidateRange(1, 15)][int]$PollSeconds = 2
)

function Stop-WizardBrowser {
    param([string]$SafeMessage)
    $failure = New-Object System.InvalidOperationException($SafeMessage)
    $failure.Data['WizardSafeMessage'] = $SafeMessage
    throw $failure
}

function Get-WizardProperty {
    param($Object, [string]$Name)
    if ($null -ne $Object) {
        $property = $Object.PSObject.Properties[$Name]
        if ($null -ne $property) { return $property.Value }
    }
    return $null
}

function ConvertFrom-WizardSecureInput {
    param([Security.SecureString]$Value)
    $pointer = [IntPtr]::Zero
    try {
        $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($Value)
        return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer)
    }
    finally {
        if ($pointer -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
    }
}

function Read-WizardInput {
    param([string]$Prompt, [switch]$Secret)
    if ($Secret) {
        $protected = Read-Host -Prompt $Prompt -AsSecureString
        if ($null -eq $protected) { Stop-WizardBrowser 'Input ended. No authorization success is assumed.' }
        try { $value = ConvertFrom-WizardSecureInput $protected }
        finally { $protected.Dispose() }
    }
    else { $value = Read-Host -Prompt $Prompt }
    if ([string]::IsNullOrWhiteSpace($value) -or $value -eq '/cancel') {
        Stop-WizardBrowser 'Input cancelled or ended. No authorization success is assumed.'
    }
    return $value
}

function ConvertTo-WizardContextUrl {
    param([string]$Text, [string]$Origin, [bool]$AllowLocal)
    $base = $null
    $url = $null
    if (-not [Uri]::TryCreate($Origin, [UriKind]::Absolute, [ref]$base) -or
        $base.UserInfo -or $base.Query -or $base.Fragment -or $base.AbsolutePath -ne '/') {
        Stop-WizardBrowser 'ServiceOrigin must be an HTTPS origin without credentials, path, query or fragment.'
    }
    $loopback = $base.Host -in @('localhost', '127.0.0.1', '[::1]', '::1')
    if ($base.Scheme -ne 'https' -and -not ($AllowLocal -and $loopback -and $base.Scheme -eq 'http')) {
        Stop-WizardBrowser 'HTTPS is required. Loopback HTTP requires explicit local development.'
    }
    if (-not [Uri]::TryCreate($Text, [UriKind]::Absolute, [ref]$url) -or
        $url.UserInfo -or $url.Query -or $url.AbsolutePath -cne '/cli/authorize' -or
        $url.GetLeftPart([UriPartial]::Authority) -cne $base.GetLeftPart([UriPartial]::Authority)) {
        Stop-WizardBrowser 'The authorization URL must match ServiceOrigin and the exact /cli/authorize path.'
    }
    $parts = @{}
    foreach ($part in $url.Fragment.TrimStart('#').Split('&')) {
        $pair = $part.Split([char[]]@('='), 2, [StringSplitOptions]::None)
        if ($pair.Count -ne 2) { Stop-WizardBrowser 'The authorization URL fragment is malformed.' }
        try {
            $name = [Uri]::UnescapeDataString($pair[0])
            $value = [Uri]::UnescapeDataString($pair[1])
        }
        catch { Stop-WizardBrowser 'The authorization URL fragment is malformed.' }
        if ($name -cnotin @('request_id', 'ticket') -or $parts.ContainsKey($name)) {
            Stop-WizardBrowser 'The authorization URL fragment has duplicate or unexpected fields.'
        }
        $parts[$name] = $value
    }
    $requestId = [Guid]::Empty
    if ($parts.Count -ne 2 -or -not [Guid]::TryParseExact($parts['request_id'], 'D', [ref]$requestId) -or
        $parts['ticket'] -cnotmatch '^[A-Za-z0-9_-]{43}$') {
        Stop-WizardBrowser 'The authorization URL needs a valid request_id and browser ticket. Never enter a CLI verifier.'
    }
    return [pscustomobject]@{ Origin = $base.GetLeftPart([UriPartial]::Authority); RequestId = $requestId.ToString(); Ticket = $parts['ticket'] }
}

function Invoke-WizardWebRequest {
    param($State, [string]$Path, [string]$Method = 'GET', [hashtable]$Body)
    # Fixed relative paths only. No redirects, certificate overrides, response/body logging.
    if ($Path -cnotin @('/api/auth/context', '/api/cli/browser/bind', '/login', '/register',
        '/api/cli/browser', '/api/cli/browser/approve', '/api/cli/browser/cancel')) {
        Stop-WizardBrowser 'Unsupported website operation.'
    }
    $headers = @{ Accept = 'application/json'; 'Cache-Control' = 'no-store' }
    if ($Method -eq 'POST') { $headers['Origin'] = $State.Origin; $headers['X-CSRF-Token'] = $State.Csrf }
    $parameters = @{
        Uri = $State.Origin + $Path; Method = $Method; WebSession = $State.Session
        Headers = $headers; TimeoutSec = $State.Timeout; MaximumRedirection = 0
        UseBasicParsing = $true; ErrorAction = 'SilentlyContinue'; ErrorVariable = 'webErrors'
        Verbose = $false; Debug = $false
    }
    if ($Method -eq 'POST') { $parameters.ContentType = 'application/json; charset=utf-8'; $parameters.Body = [Text.Encoding]::UTF8.GetBytes((ConvertTo-Json -InputObject $Body -Compress)) }
    # PS7 returns HTTP errors normally; PS5.1 exposes HttpWebResponse via ErrorRecord.
    if ($PSVersionTable.PSVersion.Major -ge 7) { $parameters.SkipHttpErrorCheck = $true }
    $response = $null; $webErrors = @(); $status = 0; $content = ''; $location = ''; $retry = 0
    try {
        try { $response = Invoke-WebRequest @parameters }
        catch { $webErrors = @($_) }
        if ($null -ne $response) {
            $status = [int]$response.StatusCode
            $content = $response.Content
            if ($content -is [byte[]]) { $content = [Text.Encoding]::UTF8.GetString($content) }
            $location = [string]$response.Headers['Location']
            [void][int]::TryParse([string]$response.Headers['Retry-After'], [ref]$retry)
        }
        else {
            foreach ($webError in $webErrors) {
                $http = Get-WizardProperty $webError.Exception 'Response'
                if ($null -eq $http) { continue }
                $status = [int]$http.StatusCode
                if ($http -is [Net.HttpWebResponse]) {
                    $location = [string]$http.Headers['Location']
                    [void][int]::TryParse([string]$http.Headers['Retry-After'], [ref]$retry)
                    # Keep rotated cookies even when WinPS represents 303 as an error.
                    foreach ($cookie in $http.Cookies) { $State.Session.Cookies.Add($cookie) }
                    try {
                        $reader = New-Object IO.StreamReader($http.GetResponseStream())
                        try { $content = $reader.ReadToEnd() } finally { $reader.Dispose() }
                    } catch { $content = '' }
                    if (-not $content -and $webError.ErrorDetails) { $content = $webError.ErrorDetails.Message }
                    $http.Close()
                }
                else {
                    # PowerShell 7 HttpResponseMessage, including redirect-limit errors.
                    $location = [string]$http.Headers.Location
                    try { $content = $http.Content.ReadAsStringAsync().GetAwaiter().GetResult() } catch { $content = '' }
                }
                break
            }
        }
        $data = $null; $malformed = $false
        if ($status -ne 303 -and $status -ne 0) {
            try {
                $data = ConvertFrom-Json -InputObject $content -ErrorAction Stop
                if ($null -eq $data -or $data -is [array] -or $data -is [string] -or $data -is [ValueType]) { $malformed = $true }
            } catch { $malformed = $true }
        }
        $errorCode = Get-WizardProperty $data 'error'
        if ($errorCode -cnotmatch '^[a-z_]{1,80}$') { $errorCode = 'request_failed' }
        if ($status -eq 0) { $errorCode = 'network_error' }
        if ($malformed) { $errorCode = 'malformed_response' }
        return [pscustomobject]@{ Status = $status; Data = $data; Code = $errorCode; Location = $location; RetryAfter = $retry; Malformed = $malformed }
    }
    finally {
        $parameters.Body = $null; $Body = $null; $content = $null; $response = $null; $webErrors = $null
    }
}

function Test-WizardCancelKey {
    try {
        if (-not [Console]::IsInputRedirected -and [Console]::KeyAvailable) {
            $pressed = [Console]::ReadKey($true)
            return $pressed.Key -eq [ConsoleKey]::C -or $pressed.Key -eq [ConsoleKey]::Escape
        }
    } catch { } # ISE and redirected input have no console; /cancel remains available at prompts.
    return $false
}

function Wait-WizardBrowser {
    param([int]$Seconds)
    for ($tick = 0; $tick -lt $Seconds * 5; $tick++) {
        if (Test-WizardCancelKey) { Stop-WizardBrowser 'Local cancellation requested. Backend confirmation is still required.' }
        Start-Sleep -Milliseconds 200
    }
}

function Invoke-WizardGet {
    param($State, [string]$Path)
    for ($attempt = 0; $attempt -lt 3; $attempt++) {
        $reply = Invoke-WizardWebRequest $State $Path
        if ($reply.Status -eq 200 -or $reply.Status -notin @(0, 429, 502, 503, 504)) { return $reply }
        if ($attempt -eq 2) { return $reply }
        $delay = [Math]::Min(120, [Math]::Max(2, $reply.RetryAfter))
        Write-Host "Temporary service/network limit. Retrying read in $delay seconds; C cancels."
        Wait-WizardBrowser $delay
    }
}

function Assert-WizardReply {
    param($Reply, [int]$Expected = 200)
    if ($Reply.Status -ne $Expected -or $Reply.Malformed) {
        $guidance = 'Check backend/database availability; restart /login if pending context was lost.'
        if ($Reply.Status -eq 429) { $guidance = 'Rate limited. Wait at least the Retry-After interval before a new attempt.' }
        if ($Reply.Status -eq 410) { $guidance = 'Authorization expired or was cancelled. Start a fresh /login.' }
        Stop-WizardBrowser ("Website operation failed (HTTP {0}, {1}). {2}" -f $Reply.Status, $Reply.Code, $guidance)
    }
}

function Get-WizardContext {
    param($State)
    $reply = Invoke-WizardGet $State '/api/auth/context'
    Assert-WizardReply $reply
    $csrf = Get-WizardProperty $reply.Data 'csrf'
    if ($csrf -isnot [string] -or $csrf -cnotmatch '^[a-f0-9]{64}$' -or
        (Get-WizardProperty $reply.Data 'cli_pending') -isnot [bool]) {
        Stop-WizardBrowser 'Malformed website session context. No authorization success is assumed.'
    }
    $State.Csrf = $csrf
    return $reply.Data
}

function Get-WizardDate {
    param($Value)
    if ($Value -isnot [string] -or $Value -notmatch '(Z|[+-][0-9]{2}:[0-9]{2})$') { Stop-WizardBrowser 'Malformed server expiration.' }
    try { return [DateTimeOffset]::Parse($Value, [Globalization.CultureInfo]::InvariantCulture) }
    catch { Stop-WizardBrowser 'Malformed server expiration.' }
}

function Assert-WizardBrowserState {
    param($State, $Data)
    if ((Get-WizardProperty $Data 'request_id') -cne $State.RequestId -or
        (Get-WizardProperty $Data 'state') -cnotin @('pending', 'approved', 'exchanged')) {
        Stop-WizardBrowser 'Malformed or mismatched authorization state. No success is assumed.'
    }
}

function Invoke-WizardBrowserCancel {
    param($State)
    $State.CancelAttempted = $true
    for ($attempt = 0; $attempt -lt 2; $attempt++) {
        $reply = Invoke-WizardWebRequest $State '/api/cli/browser/cancel' 'POST' @{}
        if ($reply.Status -eq 200 -and -not $reply.Malformed -and
            (Get-WizardProperty $reply.Data 'state') -ceq 'cancelled' -and
            (Get-WizardProperty $reply.Data 'request_id') -ceq $State.RequestId) {
            $State.TerminalConfirmed = $true
            Write-Host 'Backend confirmed cancellation of this pending request.'
            return $true
        }
        if ($reply.Status -eq 409 -and $reply.Code -eq 'already_exchanged') {
            $State.TerminalConfirmed = $true
            Write-Host 'Cancellation did not occur: the backend reports exchange already completed. Check the original CLI.'
            return $false
        }
        if ($reply.Status -notin @(0, 429, 502, 503, 504)) { break }
        if ($attempt -eq 0) { Wait-WizardBrowser ([Math]::Min(60, [Math]::Max(2, $reply.RetryAfter))) }
    }
    Write-Host 'Cancellation was NOT confirmed. Use /cancel-login in the original CLI when possible; expiry remains enforced by the backend.'
    return $false
}

function Invoke-WizardBrowserSimulator {
    param([string]$Origin, [bool]$AllowLocal, [int]$RequestTimeout = 8, [int]$PollInterval = 2)
    $state = $null
    try {
        Write-Host 'Wizard website simulator. Keep the original CLI /login terminal open. Enter /cancel at any prompt to stop.'
        $urlText = Read-WizardInput 'Paste the authorization URL printed by the CLI (hidden)' -Secret
        $contextUrl = ConvertTo-WizardContextUrl $urlText $Origin $AllowLocal
        $urlText = $null
        $state = [pscustomobject]@{
            Origin = $contextUrl.Origin; RequestId = $contextUrl.RequestId; Timeout = $RequestTimeout
            Session = (New-Object Microsoft.PowerShell.Commands.WebRequestSession); Csrf = ''
            Bound = $false; TerminalConfirmed = $false; CancelAttempted = $false
        }
        Write-Host ('Account service: ' + $state.Origin)
        $context = Get-WizardContext $state
        $binding = Invoke-WizardWebRequest $state '/api/cli/browser/bind' 'POST' @{ request_id = $contextUrl.RequestId; ticket = $contextUrl.Ticket }
        $contextUrl.Ticket = $null; $contextUrl = $null
        Assert-WizardReply $binding
        if ((Get-WizardProperty $binding.Data 'request_id') -cne $state.RequestId -or
            (Get-WizardProperty $binding.Data 'continue_to') -cnotin @('/cli/connect', '/login.html?returnTo=%2Fcli%2Fconnect')) {
            Stop-WizardBrowser 'Malformed browser binding response.'
        }
        $state.Bound = $true
        $context = Get-WizardContext $state
        for ($attempt = 0; $attempt -lt 3 -and $null -eq (Get-WizardProperty $context 'account'); $attempt++) {
            $choice = Read-WizardInput 'L: existing-account login; R: register; /cancel: cancel'
            if ($choice -notin @('l', 'L', 'r', 'R')) { Write-Host 'Choose L or R.'; continue }
            $payload = @{}; $password = $null; $confirmation = $null
            try {
                if ($choice -in @('r', 'R')) { $payload.fullName = Read-WizardInput 'Full name' }
                $payload.email = Read-WizardInput 'Email'
                $password = Read-WizardInput 'Password' -Secret
                $payload.password = $password
                $path = '/login'
                if ($choice -in @('r', 'R')) {
                    $path = '/register'
                    $confirmation = Read-WizardInput 'Confirm password (12-256 characters)' -Secret
                    if ($password -cne $confirmation) { Write-Host 'Passwords do not match. No registration was submitted.'; continue }
                    $payload.confirmPassword = $confirmation
                    if ((Read-WizardInput 'Accept the website terms for this account? Type YES') -cne 'YES') { Stop-WizardBrowser 'Registration terms were not accepted.' }
                    $payload.acceptTerms = 'on'
                }
                $auth = Invoke-WizardWebRequest $state $path 'POST' $payload
            }
            finally { $payload.Clear(); $payload = $null; $password = $null; $confirmation = $null }
            if ($auth.Status -eq 303) {
                if ($auth.Location -cne '/cli/connect') { Stop-WizardBrowser 'Unexpected authentication redirect; it was not followed.' }
            }
            elseif ($auth.Status -notin @(0, 400, 401, 409, 429, 503)) { Assert-WizardReply $auth 303 }
            # Even an ambiguous response is never interpreted as successful authentication.
            # Re-read session/account after cookie rotation instead of replaying an auth POST.
            $context = Get-WizardContext $state
            if (-not $context.cli_pending) { Stop-WizardBrowser 'Pending browser context was lost. Cancel/restart in the original CLI.' }
            if ($null -eq (Get-WizardProperty $context 'account')) {
                if ($auth.Status -eq 429) {
                    $delay = [Math]::Min(120, [Math]::Max(60, $auth.RetryAfter))
                    Write-Host "Authentication rate limited. Waiting $delay seconds; C cancels."
                    Wait-WizardBrowser $delay
                }
                else { Write-Host 'Authentication was not confirmed. Check credentials or registration fields (password 12-256 characters, terms accepted), then retry.' }
            }
        }
        $account = Get-WizardProperty $context 'account'
        $aid = [Guid]::Empty
        if ($null -eq $account) { Stop-WizardBrowser 'No authenticated account after three attempts. Start again when ready.' }
        if (-not [Guid]::TryParse([string](Get-WizardProperty $account 'id'), [ref]$aid) -or
            (Get-WizardProperty $account 'email') -isnot [string] -or
            (Get-WizardProperty $account 'full_name') -isnot [string]) { Stop-WizardBrowser 'Malformed authenticated account response.' }
        $email = [regex]::Replace($account.email, '[\p{Cc}\p{Cf}]', '?')
        $fullName = [regex]::Replace($account.full_name, '[\p{Cc}\p{Cf}]', '?')
        Write-Host ("Authenticated account: {0} <{1}> ({2})" -f $fullName, $email, $aid)
        Write-Host ('Pending CLI request: ' + $state.RequestId)
        $pending = Invoke-WizardGet $state '/api/cli/browser'
        Assert-WizardReply $pending
        Assert-WizardBrowserState $state $pending.Data
        if ($pending.Data.state -cne 'pending') { Stop-WizardBrowser 'This simulator expects a pending request; do not reuse a completed authorization URL.' }
        if ((Read-WizardInput 'Authorize THIS account for THIS terminal? Type YES, otherwise /cancel') -cne 'YES') {
            Stop-WizardBrowser 'Authorization was not approved locally.'
        }
        $approval = Invoke-WizardWebRequest $state '/api/cli/browser/approve' 'POST' @{}
        if ($approval.Status -eq 0 -or $approval.Status -ge 500) {
            $approval = Invoke-WizardGet $state '/api/cli/browser' # Recover browser state, never repeat approval blindly.
        }
        Assert-WizardReply $approval
        Assert-WizardBrowserState $state $approval.Data
        if ($approval.Data.state -cne 'approved' -or (Get-WizardProperty $approval.Data 'code') -cnotmatch '^[A-F0-9]{12}$') { Stop-WizardBrowser 'No valid approved code was supplied by the backend.' }
        $expires = Get-WizardDate (Get-WizardProperty $approval.Data 'code_expires_at')
        $requestExpiry = Get-WizardDate (Get-WizardProperty $approval.Data 'expires_at')
        Write-Host ('Authorization code: ' + $approval.Data.code)
        Write-Host ('Server code expiration (UTC): ' + $expires.UtcDateTime.ToString('o'))
        Write-Host 'Paste this code into the ORIGINAL Wizard /login terminal. C or Escape cancels while waiting.'
        while ($true) {
            if (Test-WizardCancelKey) { Stop-WizardBrowser 'Local cancellation requested. Backend confirmation is still required.' }
            $status = Invoke-WizardGet $state '/api/cli/browser'
            Assert-WizardReply $status
            Assert-WizardBrowserState $state $status.Data
            if ($status.Data.state -ceq 'exchanged') {
                $state.TerminalConfirmed = $true
                Write-Host 'Backend confirmed successful code exchange. Check the original CLI for credential verification and secure-storage success.'
                return 0
            }
            if ($status.Data.state -cne 'approved') { Stop-WizardBrowser 'Authorization state changed unexpectedly. No exchange success is assumed.' }
            if ([DateTimeOffset]::UtcNow -ge $expires -or [DateTimeOffset]::UtcNow -ge $requestExpiry) {
                Stop-WizardBrowser 'Server-defined expiration was reached while waiting; no exchange success is assumed. Start a fresh /login.'
            }
            Wait-WizardBrowser $PollInterval
        }
    }
    catch {
        $safe = $_.Exception.Data['WizardSafeMessage']
        if ($safe) { Write-Host $safe }
        else { Write-Host 'Simulator stopped because input, response, or network handling failed. No success is assumed.' }
        return 1
    }
    finally {
        if ($null -ne $state -and $state.Bound -and -not $state.TerminalConfirmed -and -not $state.CancelAttempted) {
            try { [void](Invoke-WizardBrowserCancel $state) }
            catch { Write-Host 'Cancellation was NOT confirmed. Use /cancel-login in the original CLI when possible; server expiry still applies.' }
        }
        if ($null -ne $state) { $state.Csrf = ''; $state.Session = $null }
        $context = $null; $approval = $null; $account = $null; $urlText = $null; $contextUrl = $null
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    $allowLocal = $LocalDevelopment.IsPresent -or $env:WIZARD_ACCOUNT_LOCAL_DEV -eq '1'
    exit (Invoke-WizardBrowserSimulator -Origin $ServiceOrigin -AllowLocal $allowLocal -RequestTimeout $TimeoutSeconds -PollInterval $PollSeconds)
}
