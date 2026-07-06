import React, { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { useAuth } from "@/contexts/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { toast } from "sonner";

export default function Login() {
  const nav = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState("principal@demo-college.edu");
  const [password, setPassword] = useState("Principal@123");
  const [loading, setLoading] = useState(false);

  const onSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const user = await login(email, password);
      toast.success(`Welcome, ${user.first_name}`);
      nav(user.is_super_admin ? "/super" : "/app");
    } catch (err) {
      toast.error(err.response?.data?.detail || "Login failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen grid md:grid-cols-2">
      <div className="hidden md:block relative bg-primary overflow-hidden">
        <div className="absolute inset-0 grid-lines-bg opacity-20" />
        <div className="relative h-full p-12 flex flex-col justify-between text-primary-foreground">
          <Link to="/" className="text-3xl font-display font-bold tracking-tight" data-testid="brand-link">Athena</Link>
          <div>
            <div className="overline opacity-60">The Education OS</div>
            <div className="mt-4 font-display text-4xl leading-tight">
              Sign in to your control room.
            </div>
            <p className="mt-6 text-sm max-w-md opacity-80">
              One system for students, faculty, parents, attendance, marks, analytics — and an AI that actually understands your data.
            </p>
          </div>
          <div className="text-[11px] font-mono uppercase tracking-widest opacity-50">v1.0 · Multi-tenant</div>
        </div>
      </div>
      <div className="flex items-center justify-center p-6 md:p-12">
        <Card className="w-full max-w-md border border-border rounded-sm">
          <CardHeader>
            <CardTitle className="font-display text-2xl tracking-tight">Sign in</CardTitle>
            <CardDescription>Access your organization's ERP.</CardDescription>
          </CardHeader>
          <CardContent>
            <form onSubmit={onSubmit} className="space-y-4" data-testid="login-form">
              <div className="space-y-2">
                <Label htmlFor="email">Email</Label>
                <Input id="email" type="email" value={email} onChange={(e) => setEmail(e.target.value)} required
                  className="rounded-sm" data-testid="login-email-input" />
              </div>
              <div className="space-y-2">
                <Label htmlFor="password">Password</Label>
                <Input id="password" type="password" value={password} onChange={(e) => setPassword(e.target.value)} required
                  className="rounded-sm" data-testid="login-password-input" />
              </div>
              <Button type="submit" className="w-full rounded-sm" disabled={loading} data-testid="login-submit-btn">
                {loading ? "Signing in…" : "Sign in"}
              </Button>
              <div className="text-xs text-muted-foreground">
                No account yet?{" "}
                <Link to="/register" className="text-accent hover:underline" data-testid="link-register">Register your institution</Link>
              </div>
              <div className="pt-4 border-t border-border">
                <div className="overline text-muted-foreground">Demo credentials</div>
                <div className="text-xs mt-2 font-mono space-y-1">
                  <div>principal@demo-college.edu · Principal@123</div>
                  <div>meena.iyer@demo-college.edu · Faculty@123</div>
                  <div>superadmin@platform.io · Super@123456</div>
                </div>
              </div>
            </form>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
