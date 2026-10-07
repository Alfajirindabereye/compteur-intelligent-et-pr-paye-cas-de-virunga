import { randomUUID } from "node:crypto";

export async function startPawaPayDeposit(input: {
  amount: string;
  currency: "CDF" | "USD";
  provider: "VODACOM_MPESA_COD" | "AIRTEL_COD" | "ORANGE_COD";
  phoneNumber: string;
  statementDescription: string;
}) {
  const token = process.env.PAWAPAY_API_TOKEN;
  if (!token) throw new Error("PAWAPAY_API_TOKEN non configuré");
  const depositId = randomUUID();
  const response = await fetch("https://api.sandbox.pawapay.io/v2/deposits", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      depositId,
      amount: input.amount,
      currency: input.currency,
      country: "COD",
      provider: input.provider,
      payer: {
        type: "MMO",
        accountDetails: {
          provider: input.provider,
          phoneNumber: input.phoneNumber,
        },
      },
      customerTimestamp: new Date().toISOString(),
      statementDescription: input.statementDescription,
    }),
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(`PawaPay ${response.status}: ${JSON.stringify(body)}`);
  return body;
}

export async function startFlutterwaveCheckout(input: {
  amount: number;
  currency: "CDF" | "USD";
  email: string;
  name?: string;
  phoneNumber?: string;
  redirectUrl: string;
}) {
  const secret = process.env.FLW_SECRET_KEY;
  if (!secret) throw new Error("FLW_SECRET_KEY non configuré");
  const txRef = `VSE-${randomUUID()}`;
  const response = await fetch("https://api.flutterwave.com/v3/payments", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${secret}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      tx_ref: txRef,
      amount: input.amount,
      currency: input.currency,
      redirect_url: input.redirectUrl,
      customer: {
        email: input.email,
        name: input.name,
        phone_number: input.phoneNumber,
      },
      payment_options: "card",
    }),
  });
  const body = await response.json();
  if (!response.ok)
    throw new Error(`Flutterwave ${response.status}: ${JSON.stringify(body)}`);
  return body;
}
