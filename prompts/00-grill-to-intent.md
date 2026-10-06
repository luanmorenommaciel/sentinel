Act as a Senior Cloud Architect and DevSecOps Engineer. I have an existing repository containing code and infrastructure configurations that are already built and deployed in production. 

I need to reverse-engineer and document the current state to establish a baseline, and then generate a comprehensive `/intent/core-intent.md` document for my next SDLC phase.

### Step 1: Repository Analysis

Please review the files, directory structures, and code snippets I provide next and identify the following:
1. Core Architecture: What services, applications, and frameworks are deployed?

### Step 2: Generate `intent.md`
Once you have analyzed the provided context, generate an `intent.md` document using the following structured format. Leave placeholders like `[TBD]` for any missing information so I can fill them in later.
# Project Intent Document

## 1. Executive Summary
- Project Name: [Extract from repo name or ask]
- Business Objective: [High-level goal of this new phase/intent]
- Current State: A summary of the currently deployed application and infrastructure based on the repository analysis.

## 2. Baseline Architecture (As-Is)
- Application Components: (Microservices, frontends, APIs)
- Infrastructure &amp; Cloud Resources: (Compute, networking, storage)
- Deployment &amp; Delivery (CI/CD): (How it is currently built and shipped)
- Observability: (Logging, metrics, tracing)

## 3. The New Intent (To-Be)
- Scope of Changes: What new features, infrastructure changes, or architectural shifts are being introduced in this cycle?
- Out of Scope: What is explicitly NOT being changed?

## 4. Technical Requirements &amp; Dependencies
- Required Integrations: (External APIs, databases, third-party services)
- Prerequisites: (Tooling, access rights, cluster resources)

## 5. Security &amp; Compliance
- Access Control: (Changes to IAM, RBAC)
- Data Handling: (Encryption, privacy requirements)

## 6. SDLC &amp; Deployment Strategy
- Testing Plan: (Unit, integration, security/SAST, load testing)
- Rollout Strategy: (Blue/Green, Canary, Rolling update)
- Rollback Plan: (Steps to revert to the baseline if the new intent fails)