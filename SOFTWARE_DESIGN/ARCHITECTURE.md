# Architecture
Engineering Objective → Candidate Generator(s) → Candidate Lineages → Executable Evaluation Harness → Failure Classifier → Repair Loop → Risk/Score Ranker → Independent Verification → Promotion Gate → Proof Receipt. Sponsor model generation is an adapter; evaluation, repair policy, promotion and proof are model-independent.

## GA-001 MetaForge integration

The existing VULCAN Agentic Engineering Foundry is the implementation engine for MetaForge's construction role. It consumes JANUS-authorized Workforce Spine packets, generates and tests candidate lineages, performs bounded repair, and returns proof-bearing artifacts. PROMETHEUS AIS Competition governs candidate comparison; SECA / DevOS independently adjudicates finish truth; ProofGrid holds evidence; THOTH archives lineage. VULCAN does not authorize missions or promote unverified candidates. See `GA001_METAFORGE_HANDOFF_CONTRACT.json`.
