# heliox-cli

GPU cost visibility for ML infrastructure teams — in your terminal.

```
pip install heliox-cli
heliox auth login
heliox costs summary
```

## Install

```bash
pip install heliox-cli
```

Requires Python ≥ 3.9.

## Quick Start (60 seconds)

```bash
# Authenticate
heliox auth login

# See where your GPU budget is going
heliox costs summary --days 30

# Drill into model-level spend
heliox costs by-model --limit 10

# Deploy the agent to your K8s cluster
heliox agent deploy --namespace heliox
```

## Commands

| Command | Description |
|---------|-------------|
| `heliox auth login` | Authenticate and store credentials |
| `heliox auth logout` | Clear stored credentials |
| `heliox auth whoami` | Show current user and team |
| `heliox costs summary` | Total spend, budget status, top model |
| `heliox costs by-model` | Spend broken down by model/provider |
| `heliox costs by-team` | Spend broken down by sub-team |
| `heliox costs history` | Daily cost trend with sparkline |
| `heliox jobs list` | List recent GPU jobs |
| `heliox jobs show <id>` | Detailed job information |
| `heliox jobs top` | Most expensive jobs |
| `heliox budgets list` | All budget policies |
| `heliox budgets set <project> <amount>` | Set monthly budget |
| `heliox budgets status` | Traffic-light budget health |
| `heliox anomalies list` | Active cost anomalies |
| `heliox agent deploy` | Deploy GPU agent DaemonSet |
| `heliox agent status` | Check agent pod health |
| `heliox agent logs` | Stream agent logs |
| `heliox config set` | Set CLI configuration |
| `heliox config list` | Show all configuration |

## Configuration

Config is stored at `~/.heliox/config.json`. API keys are stored securely in the OS keyring (Keychain on macOS, Secret Service on Linux, Credential Manager on Windows).

Override at runtime with environment variables:

```bash
HELIOX_API_URL=https://my-heliox.internal heliox costs summary
HELIOX_API_KEY=hx_... heliox costs summary
```

### Self-hosted API

```bash
heliox config set api-url https://heliox.your-company.com
heliox auth login
```

## Output Formats

All commands support `--output json` for scripting:

```bash
# Pipe to jq
heliox costs by-model --output json | jq '.[].total_cost'

# Export to CSV
heliox costs by-team --output csv > team-costs.csv
```

## Shell Completion

```bash
heliox --install-completion   # auto-detects bash/zsh/fish
```

## PyPI Publish

```bash
python -m build
twine upload dist/*
```

Or use the Makefile: `make publish`
