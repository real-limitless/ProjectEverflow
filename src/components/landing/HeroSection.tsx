import { Button } from "@/components/ui/button";
import { Sparkles, Github, Terminal, ChevronDown } from "lucide-react";
import ScreenshotFrame from "./ScreenshotFrame";

const highlights = [
  "Isolated microVM sandboxes",
  "OpenCode · Claude Code · Codex",
  "Live preview + desktop GUI",
  "Self-hosted Compose stack",
];

const BETA_INSTALL = `EVERFLOW_VERSION=BETA-v0.0.1 \\
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/BETA-v0.0.1/scripts/get-everflow.sh | bash`;

const ADVANCED_INSTALL = `# Inspect the bootstrap script first (recommended)
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/BETA-v0.0.1/scripts/get-everflow.sh -o get-everflow.sh
less get-everflow.sh
EVERFLOW_VERSION=BETA-v0.0.1 bash get-everflow.sh

# Manual git clone (public beta)
git clone -b BETA-v0.0.1 https://github.com/real-limitless/ProjectEverflow.git
cd ProjectEverflow
./scripts/everflow install
./scripts/everflow setup-admin
# UI → http://localhost:3000

# Latest development tip (not a pin)
curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/Development-Everflow/scripts/get-everflow.sh | bash

# Non-interactive install to a custom path
EVERFLOW_VERSION=BETA-v0.0.1 EVERFLOW_NONINTERACTIVE=1 EVERFLOW_DIR=/opt/everflow \\
  curl -fsSL https://raw.githubusercontent.com/real-limitless/ProjectEverflow/BETA-v0.0.1/scripts/get-everflow.sh | bash`;

const HeroSection = () => {
  return (
    <section className="relative flex min-h-screen items-center justify-center overflow-hidden bg-background pt-20">
      <div className="absolute inset-0 bg-gradient-to-br from-background via-muted/30 to-background" />
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: `radial-gradient(circle, hsl(207 100% 40%) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />

      <div className="container relative z-10 mx-auto px-4 py-16 lg:px-8 lg:py-20">
        <div className="mx-auto max-w-4xl text-center">
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
            <Sparkles className="h-4 w-4" />
            Public beta · Apache-2.0 · Compose-only install
          </div>

          <h1 className="font-heading text-4xl font-black leading-[1.1] tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
            <span className="text-foreground">Governance-first collaborative AI apps</span>
            <br />
            <span className="gradient-text-indigo-teal">on your infrastructure</span>
          </h1>

          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
            Teams build, review, and deploy AI-powered applications inside pre-approved boundaries.
            Every project runs in an isolated{" "}
            <span className="text-foreground/90">microsandbox microVM</span> — clients talk only to
            the Everflow API while a privileged sandbox-agent owns KVM.
          </p>

          <div className="mt-8 flex flex-wrap items-center justify-center gap-2">
            {highlights.map((item) => (
              <span
                key={item}
                className="rounded-full border border-border/80 bg-card/80 px-3 py-1 text-xs font-medium text-muted-foreground backdrop-blur sm:text-sm"
              >
                {item}
              </span>
            ))}
          </div>

          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button
              size="lg"
              className="bg-primary px-8 py-6 text-base font-semibold text-primary-foreground shadow-lg shadow-primary/25 transition-all hover:bg-primary/90 hover:shadow-xl hover:shadow-primary/30"
              asChild
            >
              <a href="#screenshots">See the product</a>
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="border-border px-8 py-6 text-base font-semibold text-foreground hover:bg-muted"
              asChild
            >
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="mr-2 h-5 w-5" /> View on GitHub
              </a>
            </Button>
          </div>

          <div className="mx-auto mt-8 max-w-2xl rounded-xl border border-border/70 bg-card/60 p-4 text-left backdrop-blur sm:p-5">
            <div className="mb-3 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-primary sm:text-xs">
              <Terminal className="h-3.5 w-3.5" />
              Pin the public beta
            </div>
            <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border/50 bg-background/80 p-3 font-mono text-[11px] leading-relaxed text-foreground/85 sm:text-xs">
              {BETA_INSTALL}
            </pre>
            <p className="mt-2 text-xs text-muted-foreground">
              Runs <code className="font-mono text-foreground/80">get-everflow.sh</code> — checks
              Docker/Podman, clones the beta tag, and starts the Compose stack.
            </p>

            <details className="group mt-4 border-t border-border/50 pt-3">
              <summary className="flex cursor-pointer list-none items-center gap-2 text-sm font-medium text-muted-foreground transition-colors hover:text-foreground [&::-webkit-details-marker]:hidden">
                <ChevronDown className="h-4 w-4 shrink-0 transition-transform group-open:rotate-180" />
                Advanced install steps
              </summary>
              <div className="mt-3 space-y-3">
                <pre className="overflow-x-auto whitespace-pre-wrap break-all rounded-lg border border-border/50 bg-background/80 p-3 font-mono text-[11px] leading-relaxed text-foreground/80 sm:text-xs">
                  {ADVANCED_INSTALL}
                </pre>
                <p className="text-xs text-muted-foreground">
                  Requires Linux, Docker or Podman Compose, and{" "}
                  <code className="font-mono text-foreground/80">/dev/kvm</code> for real microVMs.
                  See the{" "}
                  <a
                    href="https://github.com/real-limitless/ProjectEverflow/blob/BETA-v0.0.1/README.md"
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-primary underline-offset-2 hover:underline"
                  >
                    product README
                  </a>{" "}
                  for registry modes and production checklist.
                </p>
              </div>
            </details>
          </div>
        </div>

        <div className="mx-auto mt-14 max-w-5xl">
          <ScreenshotFrame
            src="/screenshots/playground/09-live-preview.png"
            alt="Everflow live preview streaming an app from an isolated project sandbox"
            caption="Live Preview — agents start apps inside the project microVM; Preview streams them with no extra host setup."
            priority
          />
        </div>
      </div>

      <div className="absolute bottom-0 left-0 right-0 h-24 bg-gradient-to-t from-background to-transparent" />
    </section>
  );
};

export default HeroSection;
