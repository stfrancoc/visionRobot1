"""Barrido de KP/KD/KA sobre la pista virtual, sin ventana gráfica.

Corre la pista completa para cada combinación de ganancias (en el
simulador realista y, para comparar, en el ideal), puntúa cada corrida
y guarda todo en un CSV dentro de capturas/. Sirve para encontrar un
punto de partida razonable antes de afinar a mano con simulador/visor.py.
"""

import csv
import itertools
import os

import config
from control.estados import MaquinaEstados
from simulador.metricas_simulacion import RecolectorMetricas
from simulador.pista_virtual import PistaVirtual, crear_pista_calibracion

RUTA_SALIDA_CSV = os.path.join(os.path.dirname(os.path.dirname(__file__)), "capturas", "barrido_ganancias.csv")

RANGO_KP = [1.0, 2.0, 3.0, 5.0, 8.0, 10.0, 15.0, 20.0, 25.0, 30.0]  # Valores de KP a probar en el barrido.
RANGO_KD = [0.0, 2.0, 5.0, 8.0, 10.0, 15.0, 20.0]  # Valores de KD a probar en el barrido.
RANGO_KA = [0.0, 5.0, 10.0, 15.0]  # Valores de KA a probar en el barrido.

PESO_ERROR_MEDIO = 1.0  # Peso del error medio absoluto en la puntuación (más bajo es mejor).
PESO_OSCILACION = 0.6  # Peso de la oscilación (cambios de signo/s) en la puntuación: penaliza KP demasiado alto.
PESO_SALIDAS_DE_PISTA = 2.0  # Peso de las salidas de pista en la puntuación: una salida pesa como mucho error acumulado.
PESO_TIEMPO_FUERA = 1.5  # Peso del tiempo fuera de pista, además del conteo de salidas.
PESO_TIEMPO_DETENIDO = 3.0  # Peso del tiempo en DETENIDO: el robot se dio por perdido y no se recupera solo, es el peor desenlace posible.

CANTIDAD_MEJORES_A_MOSTRAR = 10  # Cuántas combinaciones imprimir en la tabla final.


def _correr_pista(kp: float, kd: float, ka: float, modo_ideal: bool) -> dict:
    """Corre la pista de calibración completa con una combinación de
    ganancias y devuelve el resumen total de métricas.

    Recibe: kp, kd, ka (ganancias a probar) y modo_ideal (bool, activa o
        desactiva latencia/motores/ruido).
    Devuelve: diccionario de resumen_total() de RecolectorMetricas, con
        además 'kp', 'kd', 'ka' y 'modo_ideal'.
    Complejidad: O(n) sobre la cantidad de fotogramas de la pista.
    """
    config.KP, config.KD, config.KA = kp, kd, ka

    pista = PistaVirtual(crear_pista_calibracion(), modo_ideal=modo_ideal)
    maquina = MaquinaEstados()
    recolector = RecolectorMetricas()

    dt = config.PASO_SIMULACION_MS / 1000.0
    t = 0.0
    # Límite de pasos como salvaguarda: si una combinación de ganancias
    # deja al robot dando vueltas sin cerrar el recorrido (por ejemplo,
    # atascado en LINEA_PERDIDA/DETENIDO de forma indefinida), esto evita
    # un bucle infinito y esa corrida simplemente se puntúa con lo que
    # alcanzó a recorrer.
    limite_pasos = 20_000

    pasos = 0
    while not pista.terminado() and pasos < limite_pasos:
        resultado_linea = pista.generar_resultado_linea()
        resultado_senales = pista.generar_resultado_senales()
        comando = maquina.actualizar(resultado_linea, resultado_senales, t)
        pista.paso(comando.izquierda, comando.derecha, dt)

        tramo = pista.tramo_actual()
        nombre_tramo = tramo.nombre if tramo is not None else "fin"
        error_valido = resultado_linea.error if resultado_linea.valida else None
        recolector.registrar_paso(nombre_tramo, error_valido, comando.izquierda, comando.derecha, dt, comando.estado)

        t += dt
        pasos += 1

    resumen = recolector.resumen_total()
    resumen["kp"] = kp
    resumen["kd"] = kd
    resumen["ka"] = ka
    resumen["modo_ideal"] = modo_ideal
    resumen["recorrido_completo"] = pista.terminado()
    return resumen


def _puntuar(resumen: dict) -> float:
    """Calcula la puntuación de una corrida (más bajo es mejor).

    Recibe: resumen (dict de _correr_pista, con error_medio, oscilacion,
        salidas_de_pista y tiempo_fuera_de_pista).
    Devuelve: float, combinación ponderada que penaliza fuerte la
        oscilación y las salidas de pista.
    Complejidad: O(1).
    """
    puntuacion = (
        PESO_ERROR_MEDIO * resumen["error_medio"]
        + PESO_OSCILACION * resumen["oscilacion"]
        + PESO_SALIDAS_DE_PISTA * resumen["salidas_de_pista"]
        + PESO_TIEMPO_FUERA * resumen["tiempo_fuera_de_pista"]
        + PESO_TIEMPO_DETENIDO * resumen["tiempo_detenido_forzado"]
    )
    if not resumen["recorrido_completo"]:
        # No terminó la pista (se quedó atascado): se penaliza fuerte
        # para que nunca gane a una combinación que sí completó.
        puntuacion += 1000.0
    return puntuacion


def _barrer(modo_ideal: bool) -> list[dict]:
    """Corre la pista para todas las combinaciones de KP/KD/KA del barrido.

    Recibe: modo_ideal (bool).
    Devuelve: lista de resúmenes (uno por combinación), con 'puntuacion'
        agregada, ordenada de mejor a peor.
    Complejidad: O(|RANGO_KP| · |RANGO_KD| · |RANGO_KA| · n).
    """
    resultados = []
    for kp, kd, ka in itertools.product(RANGO_KP, RANGO_KD, RANGO_KA):
        resumen = _correr_pista(kp, kd, ka, modo_ideal)
        resumen["puntuacion"] = _puntuar(resumen)
        resultados.append(resumen)
    resultados.sort(key=lambda r: r["puntuacion"])
    return resultados


def _imprimir_tabla(titulo: str, resultados: list[dict]) -> None:
    """Imprime las mejores combinaciones en formato de tabla.

    Recibe: titulo (str) y resultados (lista ordenada de resúmenes).
    Devuelve: nada, solo imprime.
    Complejidad: O(CANTIDAD_MEJORES_A_MOSTRAR).
    """
    print(f"\n{titulo}")
    encabezado = f"{'KP':>6} {'KD':>6} {'KA':>6} {'err_medio':>10} {'err_max':>9} {'oscil/s':>8} {'salidas':>8} {'t_fuera':>8} {'t_deten':>8} {'esfuerzo':>9} {'puntuacion':>11}"
    print(encabezado)
    print("-" * len(encabezado))
    for resumen in resultados[:CANTIDAD_MEJORES_A_MOSTRAR]:
        print(
            f"{resumen['kp']:>6.1f} {resumen['kd']:>6.1f} {resumen['ka']:>6.1f} "
            f"{resumen['error_medio']:>10.4f} {resumen['error_max']:>9.4f} "
            f"{resumen['oscilacion']:>8.2f} {resumen['salidas_de_pista']:>8} "
            f"{resumen['tiempo_fuera_de_pista']:>8.2f} {resumen['tiempo_detenido_forzado']:>8.2f} "
            f"{resumen['esfuerzo_medio']:>9.2f} {resumen['puntuacion']:>11.4f}"
        )


def _guardar_csv(resultados_realista: list[dict], resultados_ideal: list[dict]) -> None:
    """Guarda todas las corridas (ambos modos) en un único CSV.

    Recibe: resultados_realista, resultados_ideal (listas de resúmenes).
    Devuelve: nada, escribe en RUTA_SALIDA_CSV.
    Complejidad: O(n) sobre la cantidad total de combinaciones.
    """
    os.makedirs(os.path.dirname(RUTA_SALIDA_CSV), exist_ok=True)
    columnas = [
        "modo_ideal", "kp", "kd", "ka", "error_medio", "error_max",
        "oscilacion", "salidas_de_pista", "tiempo_fuera_de_pista",
        "tiempo_detenido_forzado", "esfuerzo_medio", "tiempo",
        "recorrido_completo", "puntuacion",
    ]
    with open(RUTA_SALIDA_CSV, "w", newline="", encoding="utf-8") as archivo:
        escritor = csv.DictWriter(archivo, fieldnames=columnas)
        escritor.writeheader()
        for resumen in resultados_realista + resultados_ideal:
            escritor.writerow({clave: resumen[clave] for clave in columnas})
    print(f"\n[Calibrar] Barrido completo guardado en {RUTA_SALIDA_CSV}")


def ejecutar_barrido() -> None:
    """Corre el barrido completo (realista e ideal) y reporta resultados.

    Recibe: nada.
    Devuelve: nada; imprime tablas y guarda el CSV. Restaura KP/KD/KA de
        config.py al terminar, para no dejar el módulo con el último
        valor probado.
    Complejidad: O(2 · |RANGO_KP| · |RANGO_KD| · |RANGO_KA| · n).
    """
    kp_original, kd_original, ka_original = config.KP, config.KD, config.KA

    print(f"[Calibrar] Probando {len(RANGO_KP) * len(RANGO_KD) * len(RANGO_KA)} combinaciones en cada modo (semilla={config.SEMILLA_SIMULACION})...")

    resultados_realista = _barrer(modo_ideal=False)
    resultados_ideal = _barrer(modo_ideal=True)

    _imprimir_tabla(f"Mejores {CANTIDAD_MEJORES_A_MOSTRAR} combinaciones — simulador REALISTA (latencia={config.LATENCIA_MS}ms, zona muerta, ruido)", resultados_realista)
    _imprimir_tabla(f"Mejores {CANTIDAD_MEJORES_A_MOSTRAR} combinaciones — simulador IDEAL (sin latencia/motores/ruido)", resultados_ideal)

    mejor_realista = resultados_realista[0]
    mejor_ideal = resultados_ideal[0]
    print("\n[Calibrar] Comparación ideal vs. realista (mejores combinaciones de cada uno):")
    print(f"  ideal:    KP={mejor_ideal['kp']:.1f} KD={mejor_ideal['kd']:.1f} KA={mejor_ideal['ka']:.1f}  error_medio={mejor_ideal['error_medio']:.4f}  oscilacion={mejor_ideal['oscilacion']:.2f}/s")
    print(f"  realista: KP={mejor_realista['kp']:.1f} KD={mejor_realista['kd']:.1f} KA={mejor_realista['ka']:.1f}  error_medio={mejor_realista['error_medio']:.4f}  oscilacion={mejor_realista['oscilacion']:.2f}/s")

    _guardar_csv(resultados_realista, resultados_ideal)

    config.KP, config.KD, config.KA = kp_original, kd_original, ka_original


if __name__ == "__main__":
    ejecutar_barrido()
