# 🔒 Security Policy

## Supported Versions

| Version | Supported |
|---------|-----------|
| latest (main branch) | ✅ Yes |
| older commits | ⚠️ Best effort |

## Reporting a Vulnerability

If you discover a security vulnerability in this project, **please do not open a public issue.** Instead:

1. **Email:** Send a detailed report to the project maintainer via private message or email (ishakemir454@gmail.com).

2. **Include:**
   - Description of the vulnerability
   - Steps to reproduce
   - Potential impact
   - Suggested fix (if any)
3. **Response time:** We aim to acknowledge reports within **48 hours** and provide a fix or mitigation within **7 days** for critical issues.

## Security Architecture

### Sandbox Isolation

The CUA agent operates inside a **Docker container** (`trycua/cua-xfce`), which provides a layer of isolation between the AI agent and the host system:

```
┌─────────────────────────────────────┐
│  Host Machine                       │
│  ┌───────────────────────────────┐  │
│  │  Docker Container (Sandbox)   │  │
│  │  ┌─────────────────────────┐  │  │
│  │  │  XFCE Desktop (VNC)     │  │  │
│  │  │  Agent actions run HERE │  │  │
│  │  └─────────────────────────┘  │  │
│  └───────────────────────────────┘  │
│  PyQt6 UI + model API client       │
└─────────────────────────────────────┘
```

- The agent **cannot** access host files, network services, or processes directly.
- All interactions go through the container's REST API on a **localhost-only** port.
- The container has **no privileged access** to the host.

### Built-in Safety Guards

| Guard | Description |
|-------|-------------|
| **Coordinate Validation** | All click coordinates are validated to be within `[0.0, 1.0]` range before execution |
| **Repeat Detection** | Agent automatically stops if the same action is repeated consecutively (prevents infinite loops) |
| **Step Limit** | Maximum number of steps per command is enforced (`MAX_STEPS`, default: 20) |
| **Input Sanitization** | User commands are sanitized before being passed to the LLM |
| **Plan Verification** | Each plan step is verified against success criteria using the vision model before advancing |
| **API-only Model Boundary** | Model calls go through a configured OpenAI-compatible HTTPS endpoint instead of local model loading |

## Known Security Considerations

### ⚠️ LLM Prompt Injection

The agent uses a vision-language model to interpret screenshots and decide actions. Like all LLM-based systems, it is potentially susceptible to **prompt injection** attacks:

- **Risk:** Malicious text displayed on the VM screen could influence the agent's behavior.
- **Mitigation:** The agent operates in an isolated sandbox, limiting the blast radius. The repeat guard and step limit provide additional boundaries.
- **Recommendation:** Do not point the agent at untrusted websites or content without supervision.

### ⚠️ Docker Container Security

- The sandbox container runs a full Linux desktop. While isolated, Docker is **not a security boundary** equivalent to a VM.
- **Recommendation:** Keep Docker and the container image updated. Do not run the container with `--privileged` or `--net=host` flags.

### ⚠️ Network Exposure

- The container API listens on `localhost:8001` by default. It is **not** exposed to the network.
- The VNC server inside the container is also bound to localhost.
- **Recommendation:** Do not change port bindings to `0.0.0.0` in production environments.

### ⚠️ Model API Credentials

- `MODEL_API_KEY` is used from the environment or GUI runtime state.
- **Risk:** The configured provider receives screenshots and task prompts.
- **Recommendation:** Use a trusted OpenAI-compatible provider, scope API keys tightly when possible, and avoid sending sensitive screens.

## Best Practices

1. **Run in a dedicated environment** — Use a separate user account or VM for running the agent.
2. **Keep the sandbox updated** — Regularly pull the latest container image: `docker pull trycua/cua-xfce:latest`.
3. **Monitor agent actions** — Use the Mission Control UI to watch the agent in real-time; stop it if behavior seems unexpected.
4. **Limit step count** — Keep `MAX_STEPS` reasonable (default: 20) to prevent runaway executions.
5. **Review logs** — Check the structured logs after each run; export them via the JSON export feature for auditing.
6. **Do not store credentials** — Never ask the agent to handle passwords, API keys, or other secrets inside the sandbox.
7. **Network isolation** — If possible, restrict the container's outbound network access using Docker network policies.

## Dependencies & Supply Chain

Key dependencies and their security considerations:

| Package | Purpose | Trust Level |
|---------|---------|-------------|
| `PyQt6` | GUI framework | High (Qt Company) |
| `Pillow` | Image processing | High (PSF) |
| `requests` | HTTP client | High (PSF) |
| `docker` (runtime) | Container runtime | High (Docker Inc.) |

## Disclosure Policy

- We follow **coordinated disclosure** — please allow us reasonable time to fix issues before public disclosure.
- Contributors who report valid vulnerabilities will be credited in the release notes (unless they prefer anonymity).
- We do not currently have a bug bounty program.
