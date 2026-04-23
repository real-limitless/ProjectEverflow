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
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For Individuals</h3>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Vibe code any project type — frontend, backend, or GUI — entirely on your local machine.
              Your AI chatbot has full resource access with built-in safety. Clone the repo and start building in minutes.
            </p>
            <Button size="lg" className="mt-8 bg-primary hover:bg-primary/90 text-primary-foreground px-8 shadow-lg shadow-primary/20">
              <Github className="h-5 w-5 mr-2" /> Clone & Start Building
            </Button>
          </div>

          {/* Organization side */}
          <div className="glass rounded-2xl p-8 lg:p-10 relative overflow-hidden">
            <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-primary/40 to-primary/80" />
            <div className="mb-6 inline-flex h-14 w-14 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
              <Building2 className="h-7 w-7 text-primary" />
            </div>
            <h3 className="font-heading text-2xl font-bold lg:text-3xl">For Organizations</h3>
            <p className="mt-3 text-muted-foreground leading-relaxed">
              Self-host Everflow so all AI and data stays within your infrastructure.
              Full control, compliance, and visibility — with enterprise-grade guardrails built in.
            </p>
            <div className="mt-8 flex flex-col gap-3 sm:flex-row">
              <Button size="lg" className="bg-primary hover:bg-primary/90 text-primary-foreground px-8 shadow-lg shadow-primary/20">
                Self-Host Guide
              </Button>
              <Button size="lg" variant="outline" className="border-primary/50 text-primary hover:bg-primary/10">
                Talk to Community
              </Button>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
};

export default DualCTASection;
