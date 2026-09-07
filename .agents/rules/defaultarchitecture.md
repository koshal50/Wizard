---
trigger: always_on
---

cli/
├── main.py (or main.ts, or main.go)       # Entry point
├── commands/
│   ├── investigate.py                      # Handler for "investigate"
│   ├── verify.py                           # Handler for "verify"
│   ├── report.py                           # Handler for "report"
│   └── explain.py                          # Handler for "explain"
├── parser/
│   ├── command_parser.py                   # Parses raw command strings
│   └── intent_builder.py                   # Builds Intent objects from parsed commands
├── runtime_client/
│   └── client.py                           # Communicates with the Runtime Engine API
├── display/
│   ├── progress.py                         # Progress display during investigation
│   └── results.py                          # Results display after investigation
└── models/
    ├── intent.py                            # Intent data model
    └── investigation_request.py            # Investigation Request data model