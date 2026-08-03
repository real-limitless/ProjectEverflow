import { useState } from "react";
import {
  FolderPlus,
  GitBranch,
  Cpu,
  MessageSquare,
  MonitorPlay,
  Rocket,
} from "lucide-react";
import ScreenshotFrame from "./ScreenshotFrame";

const steps = [
  {
    icon: FolderPlus,
    label: "Create project",
    description:
      "Name the workspace, set a URL slug, and bind a new sandbox-backed project to your org.",
    image: "/screenshots/playground/01-create-project.png",
    imageAlt: "Create project dialog",
  },
  {
    icon: GitBranch,
    label: "Connect repos",
    description:
      "Attach Git remotes so agents and the code panel work on your real codebases.",
    image: "/screenshots/playground/02-connect-repos.png",
    imageAlt: "Connect repositories panel",
  },
  {
    icon: Cpu,
    label: "Boot microVM",
    description:
      "The platform API provisions a sandbox via sandbox-agent. Each project gets an isolated guest with harnesses ready.",
    image: "/screenshots/01-playground-home.png",
    imageAlt: "Playground home with projects",
  },
  {
    icon: MessageSquare,
    label: "Chat with agents",
    description:
      "Open Chat with OpenCode, Claude Code, or other harnesses — tools, skills, MCP, and questions stream in the workbench.",
    image: "/screenshots/playground/11-agents-skills-tools.png",
    imageAlt: "Agents skills and tools configuration",
  },
  {
    icon: MonitorPlay,
    label: "Live preview",
    description:
      "Agents start your app in the sandbox; Preview streams it live. Pair with the code editor and terminal as you iterate.",
    image: "/screenshots/playground/09-live-preview.png",
    imageAlt: "Live preview of app from sandbox",
  },
  {
    icon: Rocket,
    label: "Automate & ship",
    description:
      "Use workflows, tests, and deploy surfaces to automate project tasks and promote beyond the sandbox when ready.",
    image: "/screenshots/playground/13-workflows.png",
    imageAlt: "Workflows automation panel",
  },
];

const WorkflowSection = () => {
  const [activeStep, setActiveStep] = useState(0);
  const active = steps[activeStep];

  return (
    <section id="workflow" className="relative py-24 lg:py-32">
      <div className="container mx-auto px-4 lg:px-8">
        <div className="mx-auto mb-16 max-w-2xl text-center">
          <h2 className="font-heading text-3xl font-bold tracking-tight sm:text-4xl lg:text-5xl">
            From empty project to{" "}
            <span className="gradient-text-indigo-teal">running preview</span>
          </h2>
          <p className="mt-4 text-lg text-muted-foreground">
            Six steps the platform actually runs — with live product captures, not slide art.
          </p>
        </div>

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
                type="button"
                onClick={() => setActiveStep(index)}
                className="group relative z-10 flex w-40 flex-col items-center text-center"
              >
                <div
                  className={`mb-3 flex h-16 w-16 items-center justify-center rounded-2xl border-2 transition-all duration-300 ${
                    index <= activeStep
                      ? "scale-110 border-primary/50 bg-primary/10"
                      : "border-border bg-card hover:border-muted-foreground/30"
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

          <div className="mx-auto mt-12 grid max-w-5xl items-start gap-8 lg:grid-cols-2" key={activeStep}>
            <div className="glass rounded-2xl p-6 sm:p-8">
              <h3 className="font-heading text-xl font-bold text-foreground">{active.label}</h3>
              <p className="mt-3 leading-relaxed text-muted-foreground">{active.description}</p>
            </div>
            <ScreenshotFrame
              src={active.image}
              alt={active.imageAlt}
              className="animate-fade-in"
            />
          </div>
        </div>

        <div className="space-y-4 lg:hidden">
          {steps.map((step, index) => (
            <button
              key={step.label}
              type="button"
              onClick={() => setActiveStep(index)}
              className={`flex w-full flex-col gap-4 rounded-xl p-4 text-left transition-all ${
                index === activeStep ? "glass" : "hover:bg-muted/50"
              }`}
            >
              <div className="flex items-start gap-4">
                <div className="flex h-12 w-12 shrink-0 items-center justify-center rounded-xl bg-primary/10">
                  <step.icon className="h-6 w-6 text-primary" />
                </div>
                <div>
                  <span className="font-heading text-sm font-bold text-foreground">
                    {step.label}
                  </span>
                  {index === activeStep && (
                    <p className="mt-1 animate-fade-in text-sm text-muted-foreground">
                      {step.description}
                    </p>
                  )}
                </div>
              </div>
              {index === activeStep && (
                <img
                  src={step.image}
                  alt={step.imageAlt}
                  className="w-full rounded-xl border border-border/60"
                  loading="lazy"
                />
              )}
            </button>
          ))}
        </div>
      </div>
    </section>
  );
};

export default WorkflowSection;
