import { defineConfig, globalIgnores } from "eslint/config";
import nextVitals from "eslint-config-next/core-web-vitals";
import nextTs from "eslint-config-next/typescript";

// Flat config (ESLint 10 no longer reads .eslintrc). Same rule sets as before:
// Next.js core-web-vitals plus typescript-eslint's recommended rules.
export default defineConfig([
  ...nextVitals,
  ...nextTs,
  // eslint-plugin-react's "detect" calls context.getFilename(), which ESLint 10
  // removed; pin the major instead (keep in step with "react" in package.json).
  { settings: { react: { version: "19" } } },
  // New in eslint-config-next 16 (React Compiler rules). Every page loads its
  // data from a mount effect that this rule flags; refactor those before enabling.
  { rules: { "react-hooks/set-state-in-effect": "off" } },
  globalIgnores([".next/**", "out/**", "build/**", "next-env.d.ts"]),
]);
