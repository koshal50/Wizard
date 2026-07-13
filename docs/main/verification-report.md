# Verification Report

This document describes the structure and content of the Verification Report — the final output that Wizard produces after completing an investigation.

---

## What the Verification Report Is

The Verification Report is the final document produced by Wizard. It summarizes everything that was discovered during the investigation, explains how each conclusion was reached, and identifies what remains uncertain.

The report is saved as `verification_report.md` in the repository's root directory (or a location specified by the user).

The Verification Report is not a raw execution log. It is not a list of facts. It is a structured, human-readable document that answers the questions a developer naturally asks when opening an unfamiliar repository:

- What technologies does this project use?
- How should I run it?
- What dependencies does it need?
- How is it deployed?
- What does not work?
- What could not be verified?

Every statement in the report is traceable to evidence. Nothing is generated from AI reasoning alone.

---

## Who Generates the Report

The Report Generator subsystem of the Runtime Engine generates the Verification Report.

The Report Generator reads verified knowledge from:
- The Claim Graph (what is known about the repository)
- The Evidence Engine (what evidence supports each claim)
- The Trust Engine (how confident the system is in each claim)
- The Goal Engine (which goals were verified, which failed, which were blocked)
- The Observation Engine (execution history and key observations)

The Report Generator assembles all of this into the structured report format described below.

---

## Report Structure

Every Verification Report follows the same structure. This consistency makes reports predictable and easy to read.

---

### Section 1: Report Header

The report opens with basic metadata about the investigation.

```markdown
# Verification Report

Repository: /path/to/repository
Investigation ID: inv_abc123
Investigation Type: Verify Runtime, Verify Dependencies
Date: 2025-07-14
Duration: 4 minutes 32 seconds
Observations Collected: 87
Claims Verified: 24
Unresolved Contradictions: 2
```

---

### Section 2: Executive Summary

A short paragraph (3 to 5 sentences) summarizing what was found and what the overall assessment is.

Example:

> This repository contains a Node.js 18 web application using the Express framework. The runtime was successfully verified — the application starts and responds on port 3000. Docker containerization is present and functional. One unresolved contradiction was detected between the README documentation and the actual startup command. Three dependencies listed in package.json could not be installed due to version conflicts.

---

### Section 3: Technology Summary

A summary of the technologies detected in the repository.

```markdown
## Detected Technologies

| Technology | Type | Detection Method | Trust |
|---|---|---|---|
| Node.js 18 | Runtime | package.json + execution | High |
| Express 4.18 | Framework | package.json | High |
| MongoDB | Database | docker-compose.yml + source code | Medium |
| Docker | Containerization | Dockerfile + docker-compose.yml | High |
| Docker Compose | Orchestration | docker-compose.yml | High |
| GitHub Actions | CI/CD | .github/workflows/ | Medium |
```

---

### Section 4: Investigation Goals Summary

A table showing every goal that was generated, its final status, and a brief explanation.

```markdown
## Investigation Goals

| Goal | Status | Summary |
|---|---|---|
| Verify Runtime | Verified | Application starts successfully on port 3000 |
| Verify Node.js Dependencies | Verified | All 23 packages installed without errors |
| Verify Docker Build | Verified | Image builds in 42 seconds |
| Verify Docker Runtime | Verified | Container starts and exposes port 3000 |
| Verify CI Configuration | Partially Verified | Workflow file is valid; execution not tested |
| Verify Database Connectivity | Failed | MongoDB connection refused during test execution |
```

---

### Section 5: Runtime Analysis

Detailed findings about how the application runs.

```markdown
## Runtime Analysis

### Language and Framework
- Runtime: Node.js 18.x (verified through execution)
- Framework: Express 4.18.2 (detected in package.json, confirmed through startup logs)
- Package Manager: npm 9.x

### Entry Points
The application has one confirmed entry point:
- `npm start` → executes `node server.js`

This was verified by executing `npm start` inside the sandbox. The process started
successfully and the application became available on port 3000 within 3 seconds.

**Evidence:**
- Observation OBS-045: package.json "start" script = "node server.js"
- Observation OBS-067: npm start exit status = running (not terminated)
- Observation OBS-068: HTTP GET localhost:3000 returned 200 OK

### Build Process
No compilation step is required for this project. The application runs directly
as JavaScript.

### Environment Requirements
The following environment variables were detected as required:
- `MONGODB_URI` (referenced in server.js, not found in .env.example)
- `JWT_SECRET` (referenced in auth middleware, example value in .env.example)
- `PORT` (optional, defaults to 3000 if not set)
```

---

### Section 6: Dependency Analysis

Findings about project dependencies.

```markdown
## Dependency Analysis

### Installed Successfully
23 of 26 packages installed without errors.

### Failed to Install
| Package | Version Required | Error |
|---|---|---|
| canvas | ^2.9.0 | Native build failed: missing libcairo headers |
| sharp | ^0.31.0 | Native build failed: missing libvips |
| node-gyp | ^9.0.0 | Installed but canvas/sharp depend on it |

**Note:** These packages require system libraries that were not available in the
sandbox. This may or may not be an issue depending on whether these packages
are used in production.

**Evidence:**
- Observation OBS-023: npm install output showing 3 package failures
- Observation OBS-024: Error log from canvas build failure
```

---

### Section 7: Deployment Analysis

Findings about how the project is deployed.

```markdown
## Deployment Analysis

### Containerization
Docker is used for containerization. A Dockerfile and docker-compose.yml are both present.

**Docker Build:** Successful (42 seconds, image size 287 MB)
**Docker Runtime:** Successful (container starts, application responds on port 3000)

### Services (docker-compose.yml)
| Service | Image | Port | Status |
|---|---|---|---|
| api | node:18-alpine (built) | 3000:3000 | Verified running |
| db | mongo:6 | 27017:27017 | Started but connection failed from api |
| redis | redis:7-alpine | 6379:6379 | Verified running |

### Database Connectivity Issue
The `api` service could not connect to the `db` service during testing. This is likely
a timing issue — the MongoDB container takes several seconds to initialize, but the
API does not appear to implement connection retry logic.

**Evidence:**
- Observation OBS-071: docker-compose up output
- Observation OBS-074: api service logs showing "MongooseError: Cannot connect to MongoDB"
- Observation OBS-075: db service logs showing MongoDB is still initializing
```

---

### Section 8: Security Observations

Findings related to security configuration.

```markdown
## Security Observations

### Secrets Management
- `.env.example` is present and contains example values (good practice)
- No `.env` file was detected in the repository (appropriate — should not be committed)
- JWT_SECRET in `.env.example` is set to "your-jwt-secret-here" — this must be changed
  in production

### Hardcoded Sensitive Values
- No hardcoded API keys or passwords were found in source files

### Authentication
- JWT-based authentication is implemented in `middleware/auth.js`
- Token expiry is set to 24 hours
- No refresh token mechanism was detected

**Important: This security analysis is based on static analysis and configuration inspection.
It is not a security audit. Professional security review is recommended before production deployment.**
```

---

### Section 9: Contradictions

This section documents cases where the investigation found conflicting information.

```markdown
## Contradictions Detected

### Contradiction 1: README vs Actual Startup Command
**README states:** "Start the application with `node app.js`"
**Actual:** package.json start script runs `node server.js` (not `app.js`)

There is no `app.js` in the repository. The README appears to be outdated.

**Resolution:** Trust the package.json start script. README documentation is incorrect.

**Evidence:**
- Observation OBS-003: README.md content mentioning `node app.js`
- Observation OBS-012: package.json start script = "node server.js"
- Observation OBS-068: Execution of `npm start` succeeded using server.js

### Contradiction 2: Database Configuration
**package.json:** Lists `pg` (PostgreSQL) as a dependency
**docker-compose.yml:** Defines a `mongo` (MongoDB) service
**Source code:** Contains both PostgreSQL and MongoDB connection code

The application appears to be in transition between databases. The investigation
could not determine which database is currently active.

**Evidence:**
- Observation OBS-015: package.json dependency "pg": "^8.0.0"
- Observation OBS-019: docker-compose.yml mongo service definition
- Observation OBS-033: Source file containing pg connection code
- Observation OBS-034: Source file containing mongoose connection code
```

---

### Section 10: Unverified Areas

This section lists topics the investigation was unable to fully verify and explains why.

```markdown
## Unverified Areas

### API Endpoint Testing
The investigation detected REST API endpoints (8 routes in routes/) but could not
test them because the database connection failed during execution.

**What was found:** Route definitions in routes/users.js, routes/auth.js, routes/posts.js
**What could not be verified:** Whether endpoints respond correctly with valid data

### CI/CD Pipeline
The GitHub Actions workflow configuration is syntactically valid but was not executed
as part of this investigation. The workflow includes a test job and a deploy job.

**What was found:** Valid .github/workflows/main.yml
**What could not be verified:** Whether tests pass, whether deployment succeeds
```

---

### Section 11: Recommendations

Evidence-based recommendations for improving the repository.

```markdown
## Recommendations

### High Priority
1. **Fix database startup ordering** — Add a health check or retry mechanism in the API
   service to wait for MongoDB to become available before making connection attempts.

2. **Update README** — The startup command in README.md (`node app.js`) is incorrect.
   Update it to match the actual command (`npm start` or `node server.js`).

3. **Resolve database ambiguity** — The repository contains both PostgreSQL (pg) and
   MongoDB (mongoose) dependencies. Clarify which database is actually in use and
   remove the unused dependency.

### Medium Priority
4. **Add .env.example for MONGODB_URI** — This required variable is referenced in code
   but not documented in .env.example. Add it with an example value.

5. **Resolve canvas/sharp build failures** — If these packages are needed, add
   documentation explaining the system dependencies required (libcairo, libvips).

### Low Priority
6. **Add connection retry logic** — Several external service connections lack retry logic.
   This makes the application fragile in environments where services start at different speeds.
```

---

### Section 12: Evidence Index

A reference index linking key claims to their supporting evidence.

```markdown
## Evidence Index

| Claim | Evidence | Source |
|---|---|---|
| Runtime = Node.js 18 | OBS-012 (package.json engines), OBS-067 (execution output) | package.json, execution |
| Application starts on port 3000 | OBS-067, OBS-068 | npm start execution, HTTP test |
| Docker build succeeds | OBS-070 | docker build execution |
| MongoDB connection fails | OBS-074, OBS-075 | docker-compose logs |
| 3 packages fail to install | OBS-023, OBS-024 | npm install execution |
```

---

## Generating the Report

The report is generated automatically when the investigation converges. You can also generate a partial report at any time using:

```bash
wizard report
```

The report reflects whatever has been verified at the time of generation. If the investigation is still in progress, the report will show partial results and clearly mark which sections are incomplete.

To generate the report in JSON format (useful for processing the results programmatically):

```bash
wizard report --format json
```
