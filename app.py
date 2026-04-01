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
    errores = []

    for encoding in ["utf-8", "latin-1", "cp1252"]:
        try:
            file.seek(0)
            df = pd.read_csv(
                file,
                sep=";",
                encoding=encoding,
                decimal=",",
                thousands="."
            )
            df.columns = [str(c).strip() for c in df.columns]
            return df
        except Exception as e:
            errores.append(f"{encoding}: {e}")

    raise Exception("No se pudo leer el archivo. Detalle: " + " | ".join(errores))


# =========================
# LIMPIAR CUIT
# =========================
def limpiar_cuit(valor):
    if pd.isna(valor):
        return ""
    return "".join(ch for ch in str(valor) if ch.isdigit())


# =========================
# CONVERTIR UNA SERIE A NUMÉRICA
# =========================
def convertir_serie_numerica(serie):
    s = serie.astype(str).str.strip()

    # vacíos / nulos textuales
    s = s.replace({
        "": pd.NA,
        "nan": pd.NA,
        "None": pd.NA,
        "NaN": pd.NA,
        "<NA>": pd.NA
    })

    # quitar separador de miles y convertir decimal coma a punto
    s = s.str.replace(".", "", regex=False)
    s = s.str.replace(",", ".", regex=False)

    return pd.to_numeric(s, errors="coerce")


# =========================
# NORMALIZAR COLUMNAS NUMÉRICAS
# =========================
def normalizar_columnas_numericas(df):
    keywords_numericas = [
        "importe", "neto", "iva", "crédito", "credito", "gravado",
        "exento", "no gravado", "percepción", "percepcion",
        "retención", "retencion", "total", "subtotal", "otros tributos"
    ]

    excluir = [
        "cuit", "doc", "nro. doc", "nro doc", "punto de venta",
        "número de comprobante", "numero de comprobante",
        "comprobante", "periodo", "archivo", "fecha", "denominación",
        "denominacion", "proveedor", "vendedor", "razón social",
        "razon social", "tipo", "moneda", "cotización", "cotizacion"
    ]

    for col in df.columns:
        nombre = str(col).strip().lower()

        if any(x in nombre for x in excluir):
            continue

        if any(x in nombre for x in keywords_numericas):
            if df[col].dtype == object:
                convertido = convertir_serie_numerica(df[col])

                # solo reemplazar si realmente convirtió algo
                if convertido.notna().sum() > 0:
                    df[col] = convertido

    return df


# =========================
# DETECTAR COLUMNAS CLAVE
# =========================
def detectar_columna(df, candidatos):
    for col in df.columns:
        nombre = str(col).strip().lower()
        for c in candidatos:
            if c in nombre:
                return col
    return None


def detectar_columna_importe(df):
    prioridades = [
        ["importe total"],
        ["importe"],
        ["total"]
    ]

    for grupo in prioridades:
        for col in df.columns:
            nombre = str(col).strip().lower()
            if all(p in nombre for p in grupo):
                if pd.api.types.is_numeric_dtype(df[col]):
                    return col

    # fallback: primera columna numérica con palabra relevante
    for col in df.columns:
        nombre = str(col).strip().lower()
        if any(x in nombre for x in ["importe", "total", "neto"]):
            if pd.api.types.is_numeric_dtype(df[col]):
                return col

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

                try:
                    with zipfile.ZipFile(zip_path, "r") as zip_ref:
                        archivo_compras = None

                        for file in zip_ref.namelist():
                            nombre_archivo = file.lower()
                            if "comprobantes_compras" in nombre_archivo and nombre_archivo.endswith(".csv"):
                                archivo_compras = file
                                break

                        if archivo_compras:
                            with zip_ref.open(archivo_compras) as f:
                                df = leer_csv_seguro(f)

                                nombre_zip = uploaded_file.name.lower()
                                periodo = nombre_zip.replace("libro_iva_periodo_", "").replace("_original.zip", "")

                                df["Periodo"] = periodo
                                df["Archivo_Origen"] = uploaded_file.name
                                df["Archivo_CSV"] = archivo_compras

                                dataframes.append(df)
                        else:
                            st.warning(f"⚠️ No se encontró comprobantes_compras.csv en {uploaded_file.name}")

                except Exception as e:
                    st.error(f"❌ Error procesando {uploaded_file.name}: {e}")

        if dataframes:
            df_final = pd.concat(dataframes, ignore_index=True)

            # Normalización numérica robusta
            df_final = normalizar_columnas_numericas(df_final)

            # Ordenar por fecha si existe
            col_fecha = detectar_columna(df_final, ["fecha de emisión", "fecha de emision", "fecha"])
            if col_fecha:
                try:
                    df_final[col_fecha] = pd.to_datetime(df_final[col_fecha], errors="coerce")
                    df_final = df_final.sort_values(by=col_fecha)
                except Exception:
                    pass

            # =========================
            # PADRÓN DE PROVEEDORES
            # =========================
            col_cuit = detectar_columna(df_final, ["nro. doc. vendedor", "nro doc vendedor", "doc vendedor", "cuit"])
            col_nombre = detectar_columna(df_final, ["denominación vendedor", "denominacion vendedor", "proveedor", "vendedor", "razón social", "razon social"])
            col_importe = detectar_columna_importe(df_final)

            if col_cuit and col_nombre and col_importe:
                base_padron = df_final[[col_cuit, col_nombre, col_importe]].copy()

                base_padron["CUIT_LIMPIO"] = base_padron[col_cuit].apply(limpiar_cuit)
                base_padron["Proveedor"] = base_padron[col_nombre].astype(str).str.strip()
                base_padron["Importe_Base"] = pd.to_numeric(base_padron[col_importe], errors="coerce").fillna(0)

                # excluir filas sin CUIT limpio
                base_padron = base_padron[base_padron["CUIT_LIMPIO"] != ""].copy()

                # nombre más frecuente por CUIT
                nombres = (
                    base_padron.groupby(["CUIT_LIMPIO", "Proveedor"])
                    .size()
                    .reset_index(name="Frecuencia")
                    .sort_values(["CUIT_LIMPIO", "Frecuencia", "Proveedor"], ascending=[True, False, True])
                    .drop_duplicates(subset=["CUIT_LIMPIO"])
                    [["CUIT_LIMPIO", "Proveedor"]]
                )

                # totales por CUIT
                totales = (
                    base_padron.groupby("CUIT_LIMPIO", as_index=False)
                    .agg(
                        **{
                            "Cantidad Comprobantes": ("CUIT_LIMPIO", "size"),
                            "Importe Total": ("Importe_Base", "sum")
                        }
                    )
                )

                padron = totales.merge(nombres, on="CUIT_LIMPIO", how="left")

                # reordenar columnas
                padron = padron[
                    ["CUIT_LIMPIO", "Proveedor", "Cantidad Comprobantes", "Importe Total"]
                ].copy()

                padron["Cuenta Sugerida"] = padron["Proveedor"].apply(sugerir_cuenta)
                padron = padron.sort_values(by="Importe Total", ascending=False)

            else:
                padron = pd.DataFrame()
                st.warning(
                    "⚠️ No se pudo generar el padrón automáticamente porque no se detectaron bien las columnas clave "
                    "(CUIT, proveedor o importe)."
                )

            # =========================
            # EXPORTAR EXCEL
            # =========================
            output_path = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")

            with pd.ExcelWriter(output_path, engine="xlsxwriter") as writer:
                df_final.to_excel(writer, sheet_name="Compras_Unificadas", index=False)

                workbook = writer.book

                # formato numérico Excel
                formato_num = workbook.add_format({"num_format": "#,##0.00"})
                formato_fecha = workbook.add_format({"num_format": "dd/mm/yyyy"})

                ws1 = writer.sheets["Compras_Unificadas"]

                # aplicar formato a columnas numéricas y fecha en hoja principal
                for idx, col in enumerate(df_final.columns):
                    ancho = max(12, min(30, len(str(col)) + 2))
                    if pd.api.types.is_numeric_dtype(df_final[col]):
                        ws1.set_column(idx, idx, ancho, formato_num)
                    elif pd.api.types.is_datetime64_any_dtype(df_final[col]):
                        ws1.set_column(idx, idx, 14, formato_fecha)
                    else:
                        ws1.set_column(idx, idx, ancho)

                if not padron.empty:
                    padron.to_excel(writer, sheet_name="Padron_Proveedores", index=False)
                    ws2 = writer.sheets["Padron_Proveedores"]

                    for idx, col in enumerate(padron.columns):
                        ancho = max(14, min(35, len(str(col)) + 2))
                        if col == "Importe Total":
                            ws2.set_column(idx, idx, 16, formato_num)
                        else:
                            ws2.set_column(idx, idx, ancho)

            with open(output_path, "rb") as f:
                st.download_button(
                    "📥 Descargar Excel Completo",
                    f,
                    file_name="compras_unificadas.xlsx"
                )

            st.success(f"✅ Proceso completo. Registros procesados: {len(df_final)}")

        else:
            st.warning("⚠️ No se encontraron datos de compras")
