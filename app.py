import io
import zipfile
from pathlib import Path

import pandas as pd
import streamlit as st

OUTPUT_ENC = "cp932"


def detect_prefix(filename: str) -> str:
    if "メルカリpovo" in filename:
        return "メルカリpovo"
    if "メルカリshop" in filename:
        return "メルカリshop"
    if "メルカリ" in filename:
        return "メルカリ"
    raise ValueError("ファイル名から種類を判定できません（「メルカリ」を含むファイル名にしてください）")


def convert(data: bytes, filename: str) -> pd.DataFrame:
    prefix = detect_prefix(filename)

    # B列=注文番号, C列=注文日, G列=小計（1行目はヘッダーなのでスキップ）
    df = pd.read_excel(
        io.BytesIO(data),
        sheet_name=0,
        header=None,
        skiprows=1,
        usecols="B,C,G",
        names=["order_no", "order_date", "subtotal"],
    )
    df = df.dropna(subset=["order_no", "order_date"])
    df = df[df["subtotal"].astype(int) != 0]

    subtotal = df["subtotal"].astype(int)
    income = subtotal.where(subtotal < 0, 0).abs().replace(0, "")
    expense = subtotal.where(subtotal > 0, 0).replace(0, "")

    out = pd.DataFrame(
        {
            "日付": pd.to_datetime(df["order_date"]).dt.strftime("%Y/%m/%d"),
            "摘要": prefix + " " + df["order_no"].astype(str),
            "入金金額": income,
            "出金金額": expense,
        }
    )
    return out


def df_to_csv_bytes(df: pd.DataFrame) -> bytes:
    csv_str = df.to_csv(index=False)
    return csv_str.encode(OUTPUT_ENC, errors="replace")


# ── Streamlit UI ──────────────────────────────────────────────────────────────
st.set_page_config(page_title="メルカリ購入履歴", layout="centered")
st.markdown("# メルカリ購入履歴<br>CSV変換ツール", unsafe_allow_html=True)

uploaded = st.file_uploader(
    "メルカリ購入履歴Excelファイルを選択（複数可）",
    type=["xlsx", "xls"],
    accept_multiple_files=True,
)

current_names = tuple(sorted(uf.name for uf in uploaded)) if uploaded else ()
if st.session_state.get("_last_files") != current_names:
    st.session_state["_last_files"] = current_names
    st.session_state["_results"] = {}
    st.session_state["_errors"] = []

if uploaded:
    if st.button("▶ 変換実行", type="primary", use_container_width=True):
        results: dict = {}
        errors: list = []

        for uf in uploaded:
            data = uf.read()
            try:
                out_df = convert(data, uf.name)
                if out_df.empty:
                    errors.append(f"{uf.name}: 有効なデータ行がありません")
                    continue
                out_name = Path(uf.name).stem
                results[out_name] = df_to_csv_bytes(out_df)
            except Exception as e:
                errors.append(f"{uf.name}: {e}")

        st.session_state["_results"] = results
        st.session_state["_errors"] = errors

    if st.session_state.get("_errors"):
        for msg in st.session_state["_errors"]:
            st.error(msg)

    if st.session_state.get("_results"):
        st.subheader("ダウンロード")

        results = st.session_state["_results"]
        if len(results) > 1:
            zip_buf = io.BytesIO()
            with zipfile.ZipFile(zip_buf, "w", zipfile.ZIP_DEFLATED) as zf:
                for fname, csv_bytes in results.items():
                    zf.writestr(f"{fname}.csv", csv_bytes)
            st.download_button(
                label="⬇ すべて一括ダウンロード（ZIP）",
                data=zip_buf.getvalue(),
                file_name="mercari_import.zip",
                mime="application/zip",
                use_container_width=True,
                type="primary",
            )
            st.divider()

        for fname, csv_bytes in results.items():
            st.download_button(
                label=f"⬇ {fname}.csv",
                data=csv_bytes,
                file_name=f"{fname}.csv",
                mime="application/octet-stream",
                use_container_width=True,
            )
