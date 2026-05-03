import pandas as pd
import numpy as np
from pathlib import Path
import sys
import logging
import re
from io import StringIO

# Configuración del logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("hallazgos.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)

# ------------------------------
# 1. Normalización de IDs
# ------------------------------
def normalizar_id(id_str) -> int:
    """Convierte 'TXN-001-2026' → 1, '005' → 5, etc."""
    if pd.isna(id_str):
        return None
    s = str(id_str).strip()
    # Formato TXN-XXX-YYYY
    match = re.search(r'TXN-(\d{3})-\d{4}', s)
    if match:
        return int(match.group(1))
    # Formato simple (solo dígitos)
    digitos = re.sub(r'\D', '', s)
    if digitos:
        return int(digitos)
    return None

# ------------------------------
# 2. Carga de fuentes
# ------------------------------
def cargar_fuente_a(ruta):
    df = pd.read_csv(ruta, sep=',')
    df['id_normalizado'] = df['id_transaccion'].apply(normalizar_id)
    df['monto'] = df['monto'].astype(float).round(2)
    logger.info(f"fuente_a: {len(df)} registros, IDs: {df['id_normalizado'].tolist()}")
    return df[['id_normalizado', 'monto', 'tipo_norma']]

def cargar_fuente_b(ruta):
    with open(ruta, 'r', encoding='utf-8') as f:
        lineas = f.readlines()
    datos = []
    for linea in lineas:
        if ';' in linea and not linea.startswith('SISTEMA') and not linea.startswith('GENERADO') and not linea.startswith('---'):
            if linea.strip() and 'id_transaccion' not in linea:
                datos.append(linea.strip())
    if not datos:
        logger.error("No se encontraron líneas de datos en fuente_b.txt")
        return pd.DataFrame(columns=['id_normalizado', 'monto', 'tipo_norma'])
    df = pd.read_csv(StringIO('\n'.join(datos)), sep=';', header=None,
                     names=['id_transaccion', 'monto', 'tipo_norma'])
    df['id_normalizado'] = df['id_transaccion'].apply(normalizar_id)
    df['monto'] = df['monto'].astype(float).round(2)
    logger.info(f"fuente_b: {len(df)} registros, IDs: {df['id_normalizado'].tolist()}")
    return df[['id_normalizado', 'monto', 'tipo_norma']]

def cargar_fuente_c(ruta):
    df = pd.read_csv(ruta, sep='\t')
    df['id_normalizado'] = df['id_transaccion'].apply(normalizar_id)
    df['monto'] = df['monto'].astype(float).round(2)
    logger.info(f"fuente_c: {len(df)} registros, IDs: {df['id_normalizado'].tolist()}")
    return df[['id_normalizado', 'monto', 'tipo_norma']]

def cargar_reporte_maestro(ruta):
    df = pd.read_excel(ruta, sheet_name='Sheet1')
    df.rename(columns={
        'ID_NORMATIVO': 'id',
        'TOTAL_REPORTADO': 'total_reportado',
        'ESTADO': 'estado'
    }, inplace=True)
    df['total_reportado'] = df['total_reportado'].astype(float).round(2)
    df['id'] = df['id'].astype(int)
    logger.info(f"reporte: {len(df)} registros, IDs: {df['id'].tolist()}")
    return df

# ------------------------------
# 3. Validaciones 
# ------------------------------
def validar_integridad(reporte, ids_fuentes):
    """Retorna lista de IDs huérfanos."""
    ids_reporte = set(reporte['id'])
    huerfanos = ids_reporte - ids_fuentes
    for hid in sorted(huerfanos):
        logger.error(f"INTEGRIDAD: ID {hid} está en el reporte pero no en ninguna fuente (huérfano).")
    return list(huerfanos)

def validar_exactitud(reporte, consolidado):
    """Retorna lista de discrepancias (diccionarios)."""
    comparacion = reporte.merge(consolidado, left_on='id', right_on='id_normalizado', how='left')
    comparacion['monto'] = comparacion['monto'].fillna(0).round(2)
    errores = comparacion[~np.isclose(comparacion['total_reportado'], comparacion['monto'], rtol=1e-9, atol=1e-9)]
    discrepancias = []
    for _, row in errores.iterrows():
        diff = row['total_reportado'] - row['monto']
        logger.error(f"EXACTITUD: ID {row['id']} - Reporte: {row['total_reportado']} | "
                     f"Suma fuentes: {row['monto']} | Diferencia: {diff:.2f}")
        discrepancias.append({
            'id': row['id'],
            'valor_reporte': row['total_reportado'],
            'suma_fuentes': row['monto'],
            'diferencia': diff
        })
    return discrepancias

def validar_regla_normativa(reporte, fuentes_combinadas):
    """Retorna lista de IDs que violan la regla A1."""
    ids_con_a1 = set(fuentes_combinadas[fuentes_combinadas['tipo_norma'] == 'A1']['id_normalizado'].dropna())
    df_a1_reporte = reporte[reporte['id'].isin(ids_con_a1)]
    violaciones = df_a1_reporte[df_a1_reporte['estado'] != 'APROBADO']
    ids_violados = []
    for _, row in violaciones.iterrows():
        logger.error(f"NORMA A1: ID {row['id']} tiene tipo_norma A1 en origen, pero estado en reporte es '{row['estado']}' (debe ser APROBADO).")
        ids_violados.append(row['id'])
    return ids_violados

# ------------------------------
# 4. Resumen y assert final
# ------------------------------
def generar_resumen_y_assert(huérfanos, discrepancias, violaciones_a1):
    logger.info("\n" + "="*60)
    logger.info("RESUMEN DE VALIDACIONES")
    logger.info("="*60)

    mensaje_error = ""

    if huérfanos:
        logger.info(f"FALLA EN INTEGRIDAD: {len(huérfanos)} ID(s) huérfano(s): {huérfanos}")
        mensaje_error += f"Huérfanos: {huérfanos}\n"
    else:
        logger.info("INTEGRIDAD CORRECTA: Todos los IDs del reporte existen en las fuentes.")

    if discrepancias:
        logger.info(f"FALLA DE EXACTITUD: {len(discrepancias)} error(es) de monto:")
        for d in discrepancias:
            logger.info(f"   - ID {d['id']}: reporte={d['valor_reporte']}, suma fuentes={d['suma_fuentes']}, diferencia={d['diferencia']:.2f}")
            mensaje_error += f"Error exactitud ID {d['id']}: reporte {d['valor_reporte']} vs suma {d['suma_fuentes']}\n"
    else:
        logger.info("EXACTITUD DENTRO DE LOS LINEAMIENTOS: Todos los montos coinciden.")

    if violaciones_a1:
        logger.info(f"FALLA EN REGLA A1: {len(violaciones_a1)} ID(s) con tipo A1 pero estado no APROBADO: {violaciones_a1}")
        mensaje_error += f"Regla A1 violada por IDs: {violaciones_a1}\n"
    else:
        logger.info("REGLA A1: Todos los IDs con tipo A1 están APROBADOS.")

    if mensaje_error:
        # Lanzamos assert con todos los fallos acumulados
        assert False, f"El reporte no supera las validaciones:\n{mensaje_error}"
    else:
        logger.info("EL REPORTE SUPERA TODAS LAS VALIDACIONES EXITOSAMENTE.")

# ------------------------------
# 5. Main
# ------------------------------

def main():
    logger.info("=== INICIO DE VALIDACIÓN DEL REPORTE MAESTRO (con assert final) ===")
    # Ruta a la carpeta donde están los insumos
    base_path = Path(__file__).parent / "Datos"

    try:
        fuente_a = cargar_fuente_a(base_path / 'fuente_a.csv')
        fuente_b = cargar_fuente_b(base_path / 'fuente_b.txt')
        fuente_c = cargar_fuente_c(base_path / 'fuente_c.csv')
        reporte = cargar_reporte_maestro(base_path / 'Master_Report.xlsx')
    except Exception as e:
        logger.error(f"Error crítico al cargar archivos: {e}")
        sys.exit(1)
    

    # Consolidar fuentes
    fuentes_combinadas = pd.concat([fuente_a, fuente_b, fuente_c], ignore_index=True)
    consolidado = fuentes_combinadas.groupby('id_normalizado', as_index=False)['monto'].sum()
    consolidado['monto'] = consolidado['monto'].round(2)
    ids_fuentes = set(fuentes_combinadas['id_normalizado'].dropna().astype(int))

    # Ejecutar validaciones (acumulan)
    huerfanos = validar_integridad(reporte, ids_fuentes)
    discrepancias = validar_exactitud(reporte, consolidado)
    violaciones_a1 = validar_regla_normativa(reporte, fuentes_combinadas)

    # Resumen y assert final
    generar_resumen_y_assert(huerfanos, discrepancias, violaciones_a1)

if __name__ == "__main__":
    main()