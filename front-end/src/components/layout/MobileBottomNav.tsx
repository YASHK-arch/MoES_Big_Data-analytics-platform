import React from "react";
import { Link, useLocation } from "react-router-dom";
import { Home, Map, AlertTriangle, BarChart3, Search } from "lucide-react";

export const MobileBottomNav: React.FC = () => {
  const location = useLocation();

  const items = [
    { name: "Home", path: "/welcome", icon: Home },
    { name: "Live Map", path: "/live-map", icon: Map },
    { name: "Report", path: "/report", icon: AlertTriangle },
    { name: "Analytics", path: "/analytics", icon: BarChart3 },
    { name: "Track", path: "/track-report", icon: Search },
  ];

  return (
    <div className="fixed bottom-0 left-0 right-0 z-40 border-t border-slate-200 bg-white/95 backdrop-blur-md md:hidden">
      <nav className="flex h-16 items-center justify-around px-2">
        {items.map((item) => {
          const isActive = location.pathname === item.path;
          const Icon = item.icon;

          return (
            <Link
              key={item.name}
              to={item.path}
              className={`flex flex-col items-center justify-center space-y-1 px-3 py-1 text-[11px] font-medium transition-colors ${
                isActive
                  ? "text-blue-600 font-bold"
                  : "text-slate-500 hover:text-slate-900"
              }`}
            >
              <Icon
                className={`h-5 w-5 ${isActive ? "text-blue-600" : "text-slate-500"}`}
              />
              <span>{item.name}</span>
            </Link>
          );
        })}
      </nav>
    </div>
  );
};
