# VHS script that records docs/demo.gif — https://github.com/charmbracelet/vhs
# Prereq: API running in mock mode on :8000
#   AGENTFLOW_MOCK_MODE=true uvicorn agentflow.api.main:app
# Record: vhs docs/demo.tape

Output docs/demo.gif

Set FontSize 14
Set Width 1150
Set Height 640
Set Padding 16
Set TypingSpeed 25ms
Set Theme "Catppuccin Mocha"

Type "# 1. A clear invoice flows straight through the agent pipeline"
Enter
Sleep 800ms
Type `curl -s localhost:8000/workflows -H 'Content-Type: application/json' -d '{"document": "Invoice INV-1042 from Acme Corp. Amount due: $1,875.50 USD by 2026-07-01."}' | jq '{status, category, confidence, extraction, agents: [.audit[].agent]}'`
Enter
Sleep 4s

Type "# 2. An ambiguous document pauses for human review (graph interrupt + checkpoint)"
Enter
Sleep 800ms
Type `curl -s localhost:8000/workflows -H 'Content-Type: application/json' -d '{"document": "Scanned note: some kind of ambiguous payment request, amount unclear."}' | tee /tmp/wf.json | jq '{status, confidence, awaiting_human_review}'`
Enter
Sleep 4s

Type "# 3. A reviewer approves -> the workflow resumes from its checkpoint"
Enter
Sleep 800ms
Type `WF=$(jq -r .workflow_id /tmp/wf.json)`
Enter
Sleep 500ms
Type `curl -s localhost:8000/workflows/$WF/decision -H 'Content-Type: application/json' -d '{"approved": true, "notes": "verified against PO"}' | jq '{status, agents: [.audit[].agent]}'`
Enter
Sleep 5s
