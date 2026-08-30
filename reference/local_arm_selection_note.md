## Aug 30: Local arm selection evidence
Probes of candidate local open-weight models under the frozen harness prompt text v1.0 (system and task prompts unchanged), run 2026-08-30 on the execution machine of record (Apple M2, 24 GB, macOS; Ollama 0.33.2), via the study's Ollama adapter with num_predict 2048 and provider-default sampling. Sections: gpt-oss:20b diagnostic probes (baseline; think low, high, disabled; constrained JSON decoding; after a refreshed pull), each showing the full generation remaining in the reasoning channel with an empty final message; qwen2.5-coder:14b three-turn probes, both producing valid JSON actions. See PROTOCOL.md section 11, entry 2026-08-30, and the 2026-08-20 selection note for the original procedure.

### gpt-oss:20b output
```bash
think_false: kind=malformed eval=156 content=""
   thinking_tail="/python. We can run pip install . with that python. Or just pip? But pip might be in PATH? Let's run \"python -m pip install .\" but need to specify python? Use /usr/local/bin/python -m pip install . . We'll run in /work/qrisp. We'll output install. We'll then check exit status. We'll provide summary."
think_false2: kind=malformed eval=89 content=""
   thinking_tail="We need to install qrisp from local checkout. We are in a sandbox with no network, but we can pip install from local path. Use pip install -e .? The repository is likely structured with a setup.py or pyproject. Let's inspect the repository."
diag_nudge: kind=malformed eval=206 content=""
   thinking_tail="e that for pip? Usually pip corresponds. We can run pip from that environment. The environment might be default. Let's run \"python -m pip install -e .\" from /work/qrisp. That will install the package. Might need to use sudo? No.\n\nWe should also read the README or setup? Let's inspect the repository."
```

### qwen2.5-coder:14b output
```bash
qwen2.5-coder:14b rep1: turns=['run', 'read', 'finish']
   > "```json\n{\n  \"action\": \"run\",\n  \"command\": \"/usr/local/bin/python setup.py install\",\n  \"reason\": \"Install qrisp from the local checkout into the 
   > "```json\n{\n  \"action\": \"read\",\n  \"path\": \"requirements.txt\",\n  \"reason\": \"Check the requirements.txt file to see if numpy is listed and its versi
   > "```json\n{\n  \"action\": \"finish\",\n  \"outcome\": \"not_installed\",\n  \"summary\": \"Failed to install qrisp due to a missing requirements.txt file, whic
qwen2.5-coder:14b rep2: turns=['run', 'read', 'finish']
   > "```json\n{\n  \"action\": \"run\",\n  \"command\": \"/usr/local/bin/pip install .\",\n  \"reason\": \"Installing qrisp from the local checkout into the active 
   > "```json\n{\n  \"action\": \"read\",\n  \"path\": \"requirements.txt\",\n  \"reason\": \"Inspecting the requirements to understand the missing dependencies.\"\n
   > "```json\n{\n  \"action\": \"finish\",\n  \"outcome\": \"not_installed\",\n  \"summary\": \"Failed to install qrisp due to a missing dependency (numpy) and an a
```