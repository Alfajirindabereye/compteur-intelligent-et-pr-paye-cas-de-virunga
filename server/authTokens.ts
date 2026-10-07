import { SignJWT, jwtVerify } from "jose";

const secret = () => new TextEncoder().encode(process.env.JWT_SECRET ?? "");

export async function issueAccessToken(user: {
  id: number;
  openId: string;
  role: string;
}) {
  return new SignJWT({ openId: user.openId, role: user.role, kind: "access" })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(String(user.id))
    .setIssuedAt()
    .setExpirationTime("15m")
    .sign(secret());
}

export async function issueRefreshToken(user: {
  id: number;
  openId: string;
  role: string;
}) {
  return new SignJWT({ openId: user.openId, role: user.role, kind: "refresh" })
    .setProtectedHeader({ alg: "HS256" })
    .setSubject(String(user.id))
    .setIssuedAt()
    .setExpirationTime("30d")
    .sign(secret());
}

export async function verifyRefreshToken(token: string) {
  const result = await jwtVerify(token, secret(), { algorithms: ["HS256"] });
  if (result.payload.kind !== "refresh")
    throw new Error("refresh token attendu");
  return result.payload;
}
