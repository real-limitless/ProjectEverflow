import { useState } from "react";
import { Lightbulb, ShieldCheck, Code, GitFork, ClipboardCheck, Rocket } from "lucide-react";

const steps = [
  {
    icon: Lightbulb,
    label: "Start Idea",
    description: "Spin up a containerized workspace on your machine. Your AI chatbot connects via WebSockets — nothing leaves your environment.",
  },
  {
    icon: ShieldCheck,
    label: "Auto-Guardrails",
    description: "Instant PII scanning, toxicity checks, and policy enforcement activate in real-time. No setup required.",
  },
  {
    icon: Code,
    label: "Vibecode Freely",
    description: "Build any stack — React frontends, Python backends, desktop GUIs. The AI has full access to databases, APIs, and file systems with compliance layers active.",
  },
  {
    icon: GitFork,
    label: "Collaborate & Fork",
    description: "Share with the community, fork ideas, and co-edit with contributors.",
  },
  {
    icon: ClipboardCheck,
    label: "One-Click Review",
    description: "Community review and automated compliance checks via CI.",
  },
  {
    icon: Rocket,
    label: "Deploy Securely",
    description: "Merge to main and deploy anywhere — your infrastructure, your rules.",
  },
];

const WorkflowSection = () => {
  const [activeStep, setActiveStep] = useState(0);

  return (
    <section id="security" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            Freedom to experiment.{" "}
            <span className="gradient-text-indigo-teal">Impossible to break the rules.</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Six steps from idea to production — guardrails handle the rest.
          </p>
        </div>

        {/* Desktop horizontal timeline */}
        <div className="hidden lg:block">
          <div className="relative flex items-start justify-between">
            {/* Connector line */}
            <div className="absolute top-8 left-8 right-8 h-0.5 bg-border" />
            <div
              className="absolute top-8 left-8 h-0.5 bg-gradient-to-r from-primary to-primary/60 transition-all duration-500"
              style={{ width: `${(activeStep / (steps.length - 1)) * (100 - 8)}%` }}
            />

            {steps.map((step, index) => (
              <button
                key={step.label}
                onClick={() => setActiveStep(index)}
                className="group relative z-10 flex w-40 flex-col items-center text-center"
              >
                <div
                  className={`mb-3 flex h-16 w-16 items-center justify-center rounded-2xl border-2 transition-all duration-300 ${
                    index <= activeStep
                      ? "bg-primary/10 border-primary/50 scale-110"
                      : "bg-card border-border hover:border-muted-foreground/30"
                  }`}
                >
                  <step.icon className={`h-7 w-7 transition-colors ${index <= activeStep ? "text-primary" : "text-muted-foreground"}`} />
                </div>
                <span className={`text-sm font-semibold transition-colors ${index <= activeStep ? "text-foreground" : "text-muted-foreground"}`}>
                  {step.label}
                </span>
              </button>
            ))}
          </div>

          {/* Active description */}
          <div className="mx-auto mt-10 max-w-lg glass rounded-2xl p-6 text-center animate-fade-in" key={activeStep}>
            <p className="text-muted-foreground leading-relaxed">{steps[activeStep].description}</p>
          </div>
        </div>

        {/* Mobile vertical timeline */}
        <div className="lg:hidden space-y-4">
          {steps.map((step, index) => (
            <button
              key={step.label}
              onClick={() => setActiveStep(index)}
              className={`flex w-full items-start gap-4 rounded-xl p-4 text-left transition-all ${
                index === activeStep ? "glass" : "hover:bg-muted/50"
              }`}
            >
              <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                <step.icon className="h-6 w-6 text-primary" />
              </div>
              <div>
                <span className="font-heading text-sm font-bold text-foreground">{step.label}</span>
                {index === activeStep && (
                  <p className="mt-1 text-sm text-muted-foreground animate-fade-in">{step.description}</p>
                )}
              </div>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};

export default WorkflowSection;
