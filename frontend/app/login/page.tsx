import type { Metadata } from "next";
import LoginForm from "@/components/LoginForm";

export const metadata: Metadata = {
  title: "Sign in · Renze AI Monitoring",
};

export default function LoginPage() {
  return (
    <main className="min-h-dvh flex items-center justify-center p-4 bg-slate-50">
      <div className="w-full max-w-sm rounded-2xl border border-slate-200 bg-white p-6 shadow-sm md:p-8">
        <h1 className="text-xl font-semibold text-slate-900">Renze AI Monitoring</h1>
        <p className="mt-1 text-sm text-slate-500">Sign in to view the plant diagram.</p>
        <LoginForm />
      </div>
    </main>
  );
}
