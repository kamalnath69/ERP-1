import { Link } from "react-router-dom";

export default function AuthLegalLinks({ className = "" }) {
  return <nav aria-label="Legal links" className={`flex flex-wrap justify-center gap-x-4 gap-y-2 text-xs text-muted-foreground ${className}`}><Link to="/terms" className="hover:text-foreground">Terms</Link><Link to="/privacy" className="hover:text-foreground">Privacy</Link><Link to="/refund-policy" className="hover:text-foreground">Refund policy</Link><Link to="/#contact" className="hover:text-foreground">Contact</Link></nav>;
}
