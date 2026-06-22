import { ImageResponse } from "next/og";

export const runtime = "edge";
export const size = { width: 1200, height: 630 };
export const contentType = "image/png";

export default function Image() {
  return new ImageResponse(
    (
      <div
        style={{
          width: "100%",
          height: "100%",
          display: "flex",
          flexDirection: "column",
          justifyContent: "space-between",
          background: "#f8fafc",
          color: "#0f172a",
          padding: "72px",
          fontFamily: "Arial, sans-serif",
        }}
      >
        <div style={{ fontSize: 34, fontWeight: 700 }}>Pacer</div>
        <div style={{ display: "flex", flexDirection: "column" }}>
          <div
            style={{
              display: "flex",
              flexDirection: "column",
              fontSize: 72,
              fontWeight: 800,
              lineHeight: 1.08,
            }}
          >
            <span>6모부터 수능까지,</span>
            <span>내 정시 위치를 추적하세요.</span>
          </div>
          <div style={{ marginTop: 28, fontSize: 30, color: "#475569" }}>
            예측이 아니라 해석. 내부 데모 샘플 데이터로 확인합니다.
          </div>
        </div>
        <div
          style={{
            display: "flex",
            gap: 18,
            fontSize: 26,
            color: "#334155",
          }}
        >
          <span>성적 입력</span>
          <span>→</span>
          <span>분석 결과</span>
          <span>→</span>
          <span>AI 리포트</span>
        </div>
      </div>
    ),
    size,
  );
}
