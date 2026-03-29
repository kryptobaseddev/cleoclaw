import { betterAuth } from "better-auth";
import Database from "better-sqlite3";
import path from "node:path";
import fs from "node:fs";
import { admin, organization } from "better-auth/plugins";

const baseURL =
  process.env.BETTER_AUTH_URL ??
  process.env.NEXT_PUBLIC_BETTER_AUTH_URL ??
  "http://localhost:3010";

const databasePath =
  process.env.BETTER_AUTH_SQLITE_PATH ??
  path.join(process.cwd(), "data", "better-auth.sqlite");
fs.mkdirSync(path.dirname(databasePath), { recursive: true });

const secret =
  process.env.BETTER_AUTH_SECRET ??
  "change-me-in-env-32-plus-characters-for-better-auth";

export const auth = betterAuth({
  baseURL,
  secret,
  database: new Database(databasePath),
  emailAndPassword: {
    enabled: true,
  },
  plugins: [
    admin({
      defaultRole: "admin",
      adminRoles: ["admin"],
    }),
    organization(),
  ],
});
