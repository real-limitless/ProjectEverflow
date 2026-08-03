import { Button } from "@/components/ui/button";
import { User, Building2, Github } from "lucide-react";

const DualCTASection = () => {
  return (
    <section id="community" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="grid gap-8 lg:grid-cols-2">
          {/* Individual side */}
          <div className="glass rounded-2xl p-8 lg:p-10 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary/80 to-primary/40" />
            <div className="mb-6 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
              <User className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For builders</h3>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Clone the monorepo, bring up Compose with mock sandboxes, and open the studio —
              Chat, Code, Terminal, and Preview against a real project API. Swap in KVM microVMs
              when you are ready for production-like isolation.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Docker Compose dev stack with HMR
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Prebaked guest image for agents
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> UI demo mode without a backend
              </li>
            </ul>
            <Button
              size="lg"
              className="mt-8 bg-primary hover:bg-primary/90 text-primary-foreground px-8 shadow-lg shadow-primary/20"
              asChild
            >
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="h-5 w-5 mr-2" /> Clone & start building
              </a>
            </Button>
          </div>

          {/* Organization side */}
          <div className="glass rounded-2xl p-8 lg:p-10 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary/40 to-primary/80" />
            <div className="mb-6 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
              <Building2 className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For organizations</h3>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Self-host the platform API, sandbox-agent, and UI on your nodes. Give teams a
              governed playground — project-scoped microVMs, org membership, and a single public
              API surface — instead of unmanaged AI on laptops.
            </p>
            <ul className="mt-4 space-y-2 text-sm text-muted-foreground">
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Org-scoped projects & membership
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Isolation via microsandbox microVMs
              </li>
              <li className="flex gap-2">
                <span className="text-primary">▸</span> Data and deploys stay on your infra
              </li>
            </ul>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button
                size="lg"
                className="bg-primary hover:bg-primary/90 text-primary-foreground px-8 shadow-lg shadow-primary/20"
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
                  href="https://github.com/real-limitless/ProjectEverflow"
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
