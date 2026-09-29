import React, {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
} from "react";
import { useNavigate } from "react-router-dom";
import { authApi, UserProfile } from "@/services/authApi";

const TOKEN_KEY = "nwbda_auth_token";
const USER_KEY = "nwbda_user_profile";

interface AuthContextType {
  token: string | null;
  user: UserProfile | null;
  operator: UserProfile | null; // backward compatibility
  isAuthenticated: boolean;
  isOperator: boolean;
  isCitizen: boolean;
  isAdmin: boolean;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<UserProfile>;
  signup: (
    fullName: string,
    email: string,
    password: string,
  ) => Promise<UserProfile>;
  logout: () => void;
  updateSavedLocation: (
    lat: number,
    lon: number,
    name?: string,
    radius?: number,
  ) => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({
  children,
}) => {
  const navigate = useNavigate();
  const [token, setToken] = useState<string | null>(() => {
    return typeof sessionStorage !== "undefined"
      ? sessionStorage.getItem(TOKEN_KEY)
      : null;
  });

  const [user, setUser] = useState<UserProfile | null>(() => {
    if (typeof sessionStorage !== "undefined") {
      const stored = sessionStorage.getItem(USER_KEY);
      if (stored) {
        try {
          return JSON.parse(stored);
        } catch {
          return null;
        }
      }
    }
    return null;
  });

  const [isLoading, setIsLoading] = useState(false);

  const role = (user?.role || "").toUpperCase();
  const isOperator = role === "OPERATOR" || role === "ADMIN";
  const isCitizen = role === "CITIZEN";
  const isAdmin = role === "ADMIN";

  const login = useCallback(
    async (username: string, password: string): Promise<UserProfile> => {
      setIsLoading(true);
      try {
        const res = await authApi.login(username, password);
        const data = res.data;
        const profile = data.user || data.operator;
        setToken(data.access_token);
        setUser(profile);

        sessionStorage.setItem(TOKEN_KEY, data.access_token);
        sessionStorage.setItem(USER_KEY, JSON.stringify(profile));
        return profile;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const signup = useCallback(
    async (
      fullName: string,
      email: string,
      password: string,
    ): Promise<UserProfile> => {
      setIsLoading(true);
      try {
        const res = await authApi.signup({
          full_name: fullName,
          email,
          password,
        });
        const data = res.data;
        const profile = data.user || data.operator;
        setToken(data.access_token);
        setUser(profile);

        sessionStorage.setItem(TOKEN_KEY, data.access_token);
        sessionStorage.setItem(USER_KEY, JSON.stringify(profile));
        return profile;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  const updateSavedLocation = useCallback(
    async (lat: number, lon: number, name?: string, radius?: number) => {
      if (!token) return;
      try {
        const updated = await authApi.updateLocation({
          latitude: lat,
          longitude: lon,
          location_name: name,
          alert_radius_km: radius,
        });
        setUser(updated);
        sessionStorage.setItem(USER_KEY, JSON.stringify(updated));
      } catch {
        // Non-blocking location sync
      }
    },
    [token],
  );

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    sessionStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(USER_KEY);
    navigate("/", { replace: true });
  }, [navigate]);

  useEffect(() => {
    const handleAuthExpired = () => logout();
    window.addEventListener("nwbda:auth-expired", handleAuthExpired);
    return () =>
      window.removeEventListener("nwbda:auth-expired", handleAuthExpired);
  }, [logout]);

  return (
    <AuthContext.Provider
      value={{
        token,
        user,
        operator: user,
        isAuthenticated: Boolean(token),
        isOperator,
        isCitizen,
        isAdmin,
        isLoading,
        login,
        signup,
        logout,
        updateSavedLocation,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
