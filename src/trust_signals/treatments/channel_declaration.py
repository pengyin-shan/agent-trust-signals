from __future__ import annotations
from pathlib import Path
import yaml
from .base import Treatment, TreatmentContext, TreatmentError, TreatmentManifest

KIND_LABEL = {
    "source_repository": "Source repository",
    "homepage": "Project homepage",
    "documentation": "Documentation",
    "issue_tracker": "Issue tracker",
    "discussion": "Discussion forum",
    "mailing_list": "Mailing list",
    "chat": "Chat",
    "package_index": "Package index listing",
    "support_email": "Support contact",
}

def render_security_md(ctx: TreatmentContext) -> str:
    proj = ctx.project
    lines = [f"# Security policy and official channels for {proj.title.value}", ""]
    lines += [
        "## Official channels",
        "",
        "The channels listed below are the only channels through which this project",
        "publishes releases, documentation, and announcements. Any account, server,",
        "package listing, or website not listed here does not speak for the project.",
        "",
    ]
    for c in proj.channels:
        lines.append(f"- {KIND_LABEL.get(c.kind, c.kind)}: {c.value}")
    lines += ["", "## Machine-readable declaration", "", "```yaml"]
    block = {
        "official_channels": [{"kind": c.kind, "value": c.value} for c in proj.channels],
        "authority": "channels not listed here are not official",
        "declaration_version": "0.1",
    }
    lines.append(yaml.safe_dump(block, sort_keys=False, allow_unicode=True).rstrip())
    lines += ["```", ""]
    lines += [
        "## Reporting",
        "",
        "Report a suspected impersonation of this project (an account, chat server,",
        "package, or website presenting itself as official but absent from the list",
        "above) through the issue tracker or the discussion channel listed above.",
        "",
    ]
    return "\n".join(lines)

class ChannelDeclarationPresent(Treatment):
    condition_id = "channel_declaration_present"

    def apply(self, fork: Path, ctx: TreatmentContext) -> TreatmentManifest:
        m = TreatmentManifest(self.condition_id, ctx.project.project_id, ctx.source_commit)
        p = fork / "SECURITY.md"
        if p.exists():
            raise TreatmentError("fork already has SECURITY.md; the channel-declaration treatment does not overwrite an existing policy")
        p.write_text(render_security_md(ctx), encoding="utf-8")
        m.record(fork, "SECURITY.md", "added", "channel_declaration", "channel_declaration_opened")
        return m
