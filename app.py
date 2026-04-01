import streamlit as st
import pandas as pd
import zipfile
import os
import tempfile

st.title("📊 Contar - Unificación de Compras")

uploaded_files = st.file_uploader(
    "Subí los archivos ZIP de ARCA",
    type="zip",
    accept_multiple_files=True
)

if uploaded_files:
    if st.button("Unificar archivos"):
        dataframes = []

        with tempfile.TemporaryDirectory() as temp_dir:

            for uploaded_file in uploaded_files:
                zip_path = os.path.join(temp_dir, uploaded_file.name)

                # Guardar el ZIP temporalmente
                with open(zip_path, "wb") as f:
                    f.write(uploaded_file.read())

                # Abrir el ZIP
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    archivos = zip_ref.namelist()

                    archivo_compras = None

                    # Buscar el archivo correcto
                    for file in archivos:
                        if file.endswith("comprobantes_compras.csv"):
                            archivo_compras = file
                            break

                    if archivo_compras:
                        try:
                            with zip_ref.open(archivo_compras) as f:

                                # Intentar UTF-8, si falla usar latin-1
                                try:
                                    df = pd.read_csv(f, sep=';', encoding='utf-8')
                                except:
                                    f.seek(0)
                                    df = pd.read_csv(f, sep=';', encoding='latin-1')

                                # Agregar columnas de control
                                periodo = uploaded_file.name.replace("libro_iva_periodo_", "").replace("_original.zip", "")
                                df["Periodo"] = periodo
                                df["Archivo_Origen"] = uploaded_file.name

                                dataframes.append(df)

                        except Exception as e:
                            st.error(f"Error en {archivo_compras}: {e}")

                    else:
                        st.warning(f"No se encontró comprobantes_compras.csv en {uploaded_file.name}")

        if dataframes:
            df_final = pd.concat(dataframes, ignore_index=True)

            # Ordenar si existe la columna de fecha
            if "Fecha de Emisión" in df_final.columns:
                df_final = df_final.sort_values(by="Fecha de Emisión")

            # Exportar Excel
            output_path = os.path.join(tempfile.gettempdir(), "compras_unificadas.xlsx")

            with pd.ExcelWriter(output_path, engine='xlsxwriter') as writer:
                df_final.to_excel(writer, sheet_name="Compras_Unificadas", index=False)

            # Botón de descarga
            with open(output_path, "rb") as f:
                st.download_button(
                    "📥 Descargar Excel",
                    f,
                    file_name="compras_unificadas.xlsx"
                )

        else:
            st.warning("No se encontraron datos de compras en los archivos cargados")
