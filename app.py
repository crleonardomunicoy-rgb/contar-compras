import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile

st.title("📊 Contar - Unificación de Compras + Padrón")

uploaded_files = st.file_uploader(
    "Subí los archivos ZIP de ARCA",
    type="zip",
    accept_multiple_files=True
)

# =========================
# LECTURA SEGURA CSV
# =========================
def leer_csv_seguro(file):
    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            file.seek(0)
            return pd.read_csv(file, sep=";", encoding=encoding)
        except:
            continue
    raise Exception("No se pudo leer el archivo con ningún encoding")

# =========================
# NORMALIZACIÓN NUMÉRICA
# =========================
def normalizar_numeros(df):
    for col in df.columns:
        if df[col].dtype == object:
            try:
                df[col] = (
                    df[col]
                    .astype(str)
                    .str.replace('.', '', regex=False)
                    .str.replace(',', '.', regex=False)
                )
                df[col] = pd.to_numeric(df[col], errors='ignore')
            except:
                pass
    return df

# =========================
# LIMPIAR CUIT
# =========================
def limpiar_cuit(cuit):
    try:
        return ''.join(filter(str.isdigit, str(cuit)))
    except:
        return None

# =========================
# SUGERENCIA CONTABLE
# =========================
def sugerir_cuenta(nombre):
    nombre = str(nombre).upper()

    if any(x in nombre for x in ["YPF", "SHELL", "AXION", "COMBUST"]):
        return "Combustibles y Lubricantes"

    if any(x in nombre for x in ["TRANSP", "FLETE", "LOGIST"]):
        return "Fletes y Movilidad"

    if any(x in nombre for x in ["HONOR", "ESTUDIO", "CONSULT", "ASESOR"]):
        return "Honorarios Profesionales"

    if any(x in nombre for x in ["FERRE", "CORRALON", "MATERIALES"]):
        return "Compras de Materiales"

    if any(x in nombre for x in ["SUPER", "MERCADO", "MAYORISTA"]):
        return "Compras de Mercaderías"

    return "A revisar"

# =========================
# PROCESO PRINCIPAL
# =========================
if uploaded_files:
    if st.button("Procesar información"):

        dataframes = []

        with tempfile.TemporaryDirectory() as temp_dir:

            for uploaded_file in uploaded_files:
                zip_path = os.path.join(temp_dir, uploaded_file.name)

                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.read())

                with zipfile.ZipFile(zip_path, 'r') as zip_ref:

                    archivo_compras = None

                    for file in zip_ref.namelist():
                        if "comprobantes_compras" in file.lower() and file.endswith(".csv"):
                            archivo_compras = file
                            break

                    if archivo_compras:
                        with zip_ref.open(archivo_compras) as f:

                            df = leer_csv_seguro(f)

                            nombre_zip = uploaded_file.name.lower()
                            periodo = nombre_zip.replace("libro_iva_periodo_", "").replace("_original.zip", "")

                            df["Periodo"] = periodo
                            df["Archivo_Origen"] = uploaded_file.name

                            dataframes.append(df)

        if dataframes:

            df_final = pd.concat(dataframes, ignore_index=True)

            # Normalizar números
            df_final = normalizar_numeros(df_final)

            # =========================
            # PADRÓN DE PROVEEDORES
            # =========================

            # Detectar columnas
            col_cuit = None
            col_nombre = None
            col_importe = None

            for col in df_final.columns:
                if "doc" in col.lower():
                    col_cuit = col
                if "denom" in col.lower():
                    col_nombre = col
                if "importe" in col.lower() and col_importe is None:
                    col_importe = col

            if col_cuit and col_nombre:

                padron = df_final.copy()

                padron["CUIT_LIMPIO"] = padron[col_cuit].apply(limpiar_cuit)

                padron = padron.groupby("CUIT_LIMPIO").agg({
                    col_nombre: "last",
                    col_importe: "sum"
                }).reset_index()

                padron.rename(columns={
                    col_nombre: "Proveedor",
                    col_importe: "Importe Total"
                }, inplace=True)

                # Cantidad de comprobantes
                conteo = df_final.groupby(col_cuit).size().reset_index(name="Cantidad Comprobantes")
                conteo["CUIT_LIMPIO"] = conteo[col_cuit].apply(limpiar_cuit)

                padron = padron.merge(conteo[["CUIT_LIMPIO", "Cantidad Comprobantes"]], on="CUIT_LIMPIO", how="left")

                # Sugerencia contable
                padron["Cuenta Sugerida"] = padron["Proveedor"].apply(sugerir_cuenta)

            else:
                padron = pd.DataFrame()

            # =========================
            # EXPORTAR EXCEL
            # =========================

            output_path = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")

            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, sheet_name="Compras_Unificadas", index=False)

                if not padron.empty:
                    padron.to_excel(writer, sheet_name="Padron_Proveedores", index=False)

            with open(output_path, "rb") as f:
                st.download_button(
                    "📥 Descargar Excel Completo",
                    f,
                    file_name="compras_unificadas.xlsx"
                )

            st.success("✅ Proceso completo: compras + padrón generado")

        else:
            st.warning("No se encontraron datos de compras")
