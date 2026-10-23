"use client"
import Link from "next/link"
import { Avatar, AvatarFallback } from "./ui/avatar"
import { useAccount } from "./account-session"
export function AccountLink() {
  const { session } = useAccount()
  if (!session?.account) return null
  const initials = session.account.full_name.split(/\s+/).map(word=>word[0]).slice(0,2).join("").toUpperCase()
  return <Link href="/dashboard" className="landing-account" aria-label="Open your workspace" title={session.account.full_name}><Avatar className="size-9"><AvatarFallback className="bg-white/15 text-xs text-white">{initials}</AvatarFallback></Avatar><span>{session.account.full_name}</span></Link>
}
