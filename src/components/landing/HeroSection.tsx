import { Button } from "@/components/ui/button";
import { Sparkles, Shield, Cpu, Github } from "lucide-react";

const particles = Array.from({ length: 20 }, (_, i) => ({
  id: i,
  left: `${Math.random() * 100}%`,
  top: `${Math.random() * 100}%`,
  size: Math.random() * 4 + 2,
  delay: `${Math.random() * 6}s`,
  duration: `${4 + Math.random() * 4}s`,
}));

const highlights = [
  "Isolated microVM sandboxes",
  "OpenCode + Claude Code agents",
  "Live previews with HMR",
  "Self-hosted on your infra",
];

const HeroSection = () => {
  return (
    <section className="relative min-h-screen flex items-center justify-center overflow-hidden bg-background pt-20">
      {/* Gradient overlay */}
      <div className="absolute inset-0 bg-gradient-to-br from-background via-muted/30 to-background" />

      {/* Grid pattern */}
      <div
        className="absolute inset-0 opacity-[0.04]"
        style={{
          backgroundImage: `radial-gradient(circle, hsl(207 100% 40%) 1px, transparent 1px)`,
          backgroundSize: "40px 40px",
        }}
      />

      {/* Floating particles */}
      {particles.map((p) => (
        <div
          key={p.id}
          className="absolute rounded-full animate-float-particle"
          style={{
            left: p.left,
            top: p.top,
            width: p.size,
            height: p.size,
            background:
              p.id % 3 === 0
                ? "hsl(207 100% 40% / 0.4)"
                : p.id % 3 === 1
                  ? "hsl(207 80% 55% / 0.3)"
                  : "hsl(207 100% 65% / 0.25)",
            animationDelay: p.delay,
            animationDuration: p.duration,
          }}
        />
      ))}

      {/* Content */}
      <div className="container relative z-10 mx-auto px-4 py-20 lg:px-8">
        <div className="mx-auto max-w-4xl text-center">
          {/* Badge */}
          <div className="mb-8 inline-flex items-center gap-2 rounded-full border border-primary/30 bg-primary/10 px-4 py-1.5 text-sm font-medium text-primary">
            <Sparkles className="h-4 w-4" />
            Open source · Self-hosted · MicroVM sandboxes
          </div>

          {/* Headline */}
          <h1 className="font-heading text-4xl font-black leading-[1.1] tracking-tight sm:text-5xl md:text-6xl lg:text-7xl">
            <span className="text-foreground">From vibe prompt to production</span>
            <br />
            <span className="gradient-text-indigo-teal">on your infrastructure</span>
          </h1>

          {/* Subheadline */}
          <p className="mx-auto mt-6 max-w-2xl text-lg leading-relaxed text-muted-foreground sm:text-xl">
            Everflow is the governance-first AI development studio for teams. Spin up an isolated
            microVM per project, chat with coding agents, edit code, stream a live preview, and
            deploy — without giving AI free rein on your fleet.
          </p>

          {/* Feature chips */}
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

          {/* CTAs */}
          <div className="mt-10 flex flex-col items-center gap-4 sm:flex-row sm:justify-center">
            <Button
              size="lg"
              className="bg-primary hover:bg-primary/90 text-primary-foreground px-8 py-6 text-base font-semibold shadow-lg shadow-primary/25 transition-all hover:shadow-xl hover:shadow-primary/30"
              asChild
            >
              <a href="#features">Explore features</a>
            </Button>
            <Button
              size="lg"
              variant="outline"
              className="border-border text-foreground hover:bg-muted px-8 py-6 text-base font-semibold"
              asChild
            >
              <a
                href="https://github.com/real-limitless/ProjectEverflow"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Github className="h-5 w-5 mr-2" /> View on GitHub
              </a>
            </Button>
          </div>

          {/* Visual: create freely → ship safely */}
          <div className="mt-16 flex items-center justify-center gap-6 sm:gap-8">
            <div className="flex flex-col items-center gap-3">
              <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
                <Sparkles className="h-10 w-10 text-primary" />
              </div>
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Vibe freely
              </span>
            </div>

            <div className="flex items-center gap-1">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-0.5 w-3 rounded-full sm:w-4"
                  style={{
                    background: `hsl(207 100% 40% / ${0.2 + i * 0.15})`,
                  }}
                />
              ))}
            </div>

            <div className="flex flex-col items-center gap-3">
              <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20">
                <Cpu className="h-10 w-10 text-primary" />
              </div>
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                MicroVM isolate
              </span>
            </div>

            <div className="hidden items-center gap-1 sm:flex">
              {[...Array(5)].map((_, i) => (
                <div
                  key={i}
                  className="h-0.5 w-4 rounded-full"
                  style={{
                    background: `hsl(207 100% 40% / ${0.2 + i * 0.15})`,
                  }}
                />
              ))}
            </div>

            <div className="hidden flex-col items-center gap-3 sm:flex">
              <div className="relative flex h-20 w-20 items-center justify-center rounded-2xl bg-primary/10 border border-primary/20 animate-pulse-glow">
                <Shield className="h-10 w-10 text-primary" />
              </div>
              <span className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
                Ship safely
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom gradient fade */}
      <div className="absolute bottom-0 left-0 right-0 h-32 bg-gradient-to-t from-background to-transparent" />
    </section>
  );
};

export default HeroSection;
