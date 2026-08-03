import { useState } from "react";
import {
  FolderPlus,
  Cpu,
  MessageSquare,
  Code2,
  MonitorPlay,
  Rocket,
} from "lucide-react";

const steps = [
  {
    icon: FolderPlus,
    label: "Create project",
    description:
      "Multi-step wizard: pick a template, enable harnesses (OpenCode, Claude Code, CI, preview, deploy), and attach the project to your org.",
  },
  {
    icon: Cpu,
    label: "Boot microVM",
    description:
      "The platform API provisions a sandbox via sandbox-agent. Create returns once the guest is up; harness install continues in the background on a prebaked image.",
  },
  {
    icon: MessageSquare,
    label: "Chat with agents",
    description:
      "Open the Chat panel and stream OpenCode sessions — tool calls, file edits, and clarifying questions appear inline while the sandbox runs the work.",
  },
  {
    icon: Code2,
    label: "Edit & shell",
    description:
      "Jump into the Code panel or an interactive terminal. Multi-repo git, nested file trees, and live sessions stay available while you iterate.",
  },
  {
    icon: MonitorPlay,
    label: "Live preview",
    description:
      "Port discovery finds services in the guest. Mint a GUID-hosted preview endpoint and load the app with WebSocket HMR through the platform proxy.",
  },
  {
    icon: Rocket,
    label: "Deploy",
    description:
      "Use the Deploy workbench for remote podman-compose style shipping — promote from sandbox iterate to infrastructure you control.",
  },
];

const WorkflowSection = () => {
  const [activeStep, setActiveStep] = useState(0);

  return (
    <section id="workflow" className="relative py-24 lg:py-32 bg-muted/30">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            From empty project to{" "}
            <span className="gradient-text-indigo-teal">running preview</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Six steps the platform actually runs — not a slide-deck fantasy.
          </p>
        </div>

        {/* Desktop horizontal timeline */}
        <div className="hidden lg:block">
          <div className="relative flex items-start justify-between">
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
                  <step.icon
                    className={`h-7 w-7 transition-colors ${
                      index <= activeStep ? "text-primary" : "text-muted-foreground"
                    }`}
                  />
                </div>
                <span
                  className={`text-sm font-semibold transition-colors ${
                    index <= activeStep ? "text-foreground" : "text-muted-foreground"
                  }`}
                >
                  {step.label}
                </span>
              </button>
            ))}
          </div>

          <div
            className="mx-auto mt-10 max-w-lg glass rounded-2xl p-6 text-center animate-fade-in"
            key={activeStep}
          >
            <p className="text-muted-foreground leading-relaxed">
              {steps[activeStep].description}
            </p>
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
                <span className="font-heading text-sm font-bold text-foreground">
                  {step.label}
                </span>
                {index === activeStep && (
                  <p className="mt-1 text-sm text-muted-foreground animate-fade-in">
                    {step.description}
                  </p>
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
