import { Button } from "@/components/ui/button";
import { User, Building2, Github, Terminal } from "lucide-react";

const DualCTASection = () => {
  return (
    <section id="community" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2">
          <div className="glass relative overflow-hidden rounded-2xl p-8 lg:p-10">
            <div className="absolute left-0 right-0 top-0 h-1 bg-gradient-to-r from-primary/80 to-primary/40" />
            <div className="mb-6 inline-flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10">
              <User className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For builders</h3>
            <p className="mt-3 leading-relaxed text-muted-foreground">
              Clone a product ref, run the install TUI, and open the studio at localhost:3000 —
              playground workbench, marketplace, and harnesses against a real project API.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Pin{" "}
                <code className="rounded bg-muted px-1 font-mono text-xs">BETA-v0.0.1</code> or tip{" "}
                <code className="rounded bg-muted px-1 font-mono text-xs">Development-Everflow</code>
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span>{" "}
                <code className="rounded bg-muted px-1 font-mono text-xs">./scripts/everflow install</code>
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Dev compose hot reload still via Compose only
              </li>
            </ul>
            <div className="mt-6 rounded-xl border border-border/60 bg-background/80 p-4 font-mono text-xs text-muted-foreground">
              <div className="mb-2 flex items-center gap-2 text-[10px] font-semibold uppercase tracking-wider text-primary">
                <Terminal className="h-3.5 w-3.5" />
                Quick path
              </div>
              <p className="text-foreground/85">./scripts/everflow setup-admin</p>
              <p className="text-foreground/85"># UI → http://localhost:3000</p>
            </div>
            <Button
              size="lg"
              className="mt-8 bg-primary px-8 text-primary-foreground shadow-lg shadow-primary/20 hover:bg-primary/90"
              asChild
            >
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="mr-2 h-5 w-5" /> Clone & start building
              </a>
            </Button>
          </div>

          <div className="glass relative overflow-hidden rounded-2xl p-8 lg:p-10">
            <div className="absolute left-0 right-0 top-0 h-1 bg-gradient-to-r from-primary/40 to-primary/80" />
            <div className="mb-6 inline-flex h-14 w-14 items-center justify-center rounded-2xl border border-primary/20 bg-primary/10">
              <Building2 className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For organizations</h3>
            <p className="mt-3 leading-relaxed text-muted-foreground">
              Self-host the platform API, sandbox-agent, UI, registry, and SearXNG on your nodes.
              Give teams a governed playground instead of unmanaged AI on laptops.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Org-scoped projects, membership & plans
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Isolation via microsandbox microVMs
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Data, credentials, and deploys stay on your infra
              </li>
            </ul>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button
                size="lg"
                className="bg-primary px-8 text-primary-foreground shadow-lg shadow-primary/20 hover:bg-primary/90"
                asChild
              >
                <a href="#architecture">Self-host architecture</a>
              </Button>
              <Button
                size="lg"
                variant="outline"
                className="border-primary/50 text-primary hover:bg-primary/10"
                asChild
              >
                <a
                  href="https://github.com/real-limitless/ProjectEverflow/blob/Development-Everflow/README.md"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Read the README
                </a>
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default DualCTASection;
