import { ImageResponse } from "next/og";

export const runtime = "edge";
export const alt =
  "Barreiras 360 — transparência pública de Barreiras com fonte em cada registro";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function OpenGraphImage() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          padding: "72px 80px",
          background: "linear-gradient(135deg, #f5f7fb 0%, #e8eefb 100%)",
          color: "#111522",
          fontFamily: "sans-serif",
        }}
      >
        <div
          style={{
            display: "flex",
            alignItems: "center",
            gap: "16px",
            fontSize: 34,
            fontWeight: 700,
            color: "#0d4ea9",
          }}
        >
          Barreiras 360
        </div>
        <div style={{ display: "flex", flexDirection: "column", gap: "18px" }}>
          <div style={{ fontSize: 72, fontWeight: 700, lineHeight: 1.08 }}>
            Barreiras, vista por inteiro.
          </div>
          <div style={{ fontSize: 34, color: "#3d4759", lineHeight: 1.3 }}>
            Dinheiro público, decisões e representantes — com o documento
            oficial em cada registro.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            fontSize: 26,
            color: "#606a7c",
          }}
        >
          <div>Fonte verificável · Cálculos reproduzíveis</div>
          <div>barreiras-em-dados.vercel.app</div>
        </div>
      </div>
    ),
    size,
  );
}
