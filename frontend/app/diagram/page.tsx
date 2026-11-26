import type { Metadata } from "next";
import DiagramView from "@/components/DiagramView";

export const metadata: Metadata = {
  title: "Plant diagram · Renze AI Monitoring",
};

export default function DiagramPage() {
  return <DiagramView />;
}
