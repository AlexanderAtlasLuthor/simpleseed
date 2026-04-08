/**
 * Module augmentation to extend NextAuth's built-in TypeScript types.
 *
 * Adds `accessToken` (the FastAPI JWT) to the Session type so TypeScript
 * knows about the extra field we add in the `session` callback in route.ts.
 *
 * Also adds `id` to Session.user so we can access the user's DB UUID.
 */
import "next-auth";
import "next-auth/jwt";

declare module "next-auth" {
  interface Session {
    /** FastAPI JWT — attach as `Authorization: Bearer <accessToken>` */
    accessToken: string;
    user: {
      id: string;
      email?: string | null;
      name?: string | null;
      image?: string | null;
    };
  }

  interface User {
    /** FastAPI JWT returned from the login endpoint */
    accessToken: string;
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    accessToken?: string;
    userId?: string;
  }
}
