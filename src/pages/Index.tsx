import Navbar from "@/components/landing/Navbar";
import HeroSection from "@/components/landing/HeroSection";
import FeaturesSection from "@/components/landing/FeaturesSection";
import StudioSection from "@/components/landing/StudioSection";
import ArchitectureSection from "@/components/landing/ArchitectureSection";
import WorkflowSection from "@/components/landing/WorkflowSection";
import PlaygroundSection from "@/components/landing/PlaygroundSection";
import DualCTASection from "@/components/landing/DualCTASection";
import TrustFooter from "@/components/landing/TrustFooter";

const Index = () => {
  return (
    <div className="min-h-screen bg-background">
      <Navbar />
      <main>
        <HeroSection />
        <FeaturesSection />
        <StudioSection />
        <ArchitectureSection />
        <WorkflowSection />
        <PlaygroundSection />
        <DualCTASection />
        <TrustFooter />
      </main>
    </div>
  );
};

export default Index;
