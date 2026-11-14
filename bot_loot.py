"""Bot de loot para otPokemon, com cliques restritos à janela do jogo."""

import json
import os
import queue
import sys
import threading
import time
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk


NOME_JANELA = "otPokemon"
ARQUIVO_CONFIG = "bot_loot_config.json"
ALTURA_MODELO = 0.65
LARGURA_FALLBACK = 320
ALTURA_FALLBACK = 240


def pasta_programa():
    """Retorna a pasta do executável ou, durante desenvolvimento, deste arquivo."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


class ErroBot(RuntimeError):
    """Falha operacional que pode ser mostrada diretamente na interface."""


class MotorLoot:
    """Um ciclo de loot com callbacks substituíveis para testes simulados."""

    def __init__(
        self,
        tamanho_cliente,
        ponto_corpo,
        area_loot,
        itens,
        precisao,
        capturar,
        clicar,
        localizar,
        obter_tamanho=None,
        aguardar=time.sleep,
        pausa_abertura=0.15,
    ):
        self.largura, self.altura = tamanho_cliente
        self.ponto_corpo = tuple(ponto_corpo)
        self.area_loot = tuple(area_loot) if area_loot else None
        self.itens = itens
        self.precisao = precisao
        self.capturar = capturar
        self.clicar = clicar
        self.localizar = localizar
        self.obter_tamanho = obter_tamanho
        self.aguardar = aguardar
        self.pausa_abertura = pausa_abertura

    def _validar_ponto_corpo(self):
        if self.obter_tamanho and tuple(self.obter_tamanho()) != (
            self.largura,
            self.altura,
        ):
            raise ErroBot(
                "O tamanho da janela do jogo mudou. Marque novamente as posições."
            )
        x, y = self.ponto_corpo
        if not (0 <= x < self.largura and 0 <= y < self.altura):
            raise ErroBot("O ponto do corpo está fora da área cliente do jogo.")

    def _obter_area_segura(self):
        if self.area_loot:
            x1, y1, x2, y2 = self.area_loot
            if not (0 <= x1 < x2 <= self.largura and 0 <= y1 < y2 <= self.altura):
                raise ErroBot("A área de loot está fora dos limites atuais do jogo.")
            if x2 - x1 < 8 or y2 - y1 < 8:
                raise ErroBot("A área de loot marcada é pequena demais.")
            return x1, y1, x2, y2

        # Sem seleção manual, restringe a procura a uma caixa pequena ancorada
        # no ponto em que o corpo é aberto; nunca usa a janela inteira.
        x, y = self.ponto_corpo
        x2 = min(self.largura, x + LARGURA_FALLBACK)
        y2 = min(self.altura, y + ALTURA_FALLBACK)
        if x2 - x < 8 or y2 - y < 8:
            raise ErroBot(
                "Marque uma área de loot: o ponto do corpo não deixa espaço "
                "suficiente para a região segura padrão."
            )
        return x, y, x2, y2

    def executar_ciclo(self):
        """Abre o corpo e clica apenas em correspondências dentro da área segura."""
        self._validar_ponto_corpo()
        area = self._obter_area_segura()

        # O único clique no corpo é exatamente no ponto salvo.
        self.clicar(self.ponto_corpo[0], self.ponto_corpo[1])
        self.aguardar(self.pausa_abertura)
        quadro = self.capturar()
        if quadro is None or len(quadro.shape) < 2:
            raise ErroBot("A captura da janela do jogo está vazia ou inválida.")
        altura_quadro, largura_quadro = quadro.shape[:2]
        if (largura_quadro, altura_quadro) != (self.largura, self.altura):
            raise ErroBot(
                "O tamanho da janela do jogo mudou. Marque novamente as posições."
            )

        correspondencias = self.localizar(
            quadro, self.itens, area, self.precisao
        )
        x1, y1, x2, y2 = area
        cliques = 0
        ja_clicados = set()
        for item in correspondencias:
            if (
                not isinstance(item, (tuple, list))
                or len(item) != 4
                or any(type(valor) is not int for valor in item)
            ):
                continue
            x, y, largura, altura = item
            if largura <= 0 or altura <= 0:
                continue
            # A caixa inteira do item, e não somente seu centro, precisa estar
            # dentro da região marcada/derivada e da área cliente capturada.
            if not (
                x1 <= x
                and y1 <= y
                and x + largura <= x2
                and y + altura <= y2
                and 0 <= x
                and 0 <= y
                and x + largura <= largura_quadro
                and y + altura <= altura_quadro
            ):
                continue
            centro = (x + largura // 2, y + altura // 2)
            if centro in ja_clicados:
                continue
            ja_clicados.add(centro)
            self.clicar(*centro)
            cliques += 1
        return cliques


def localizar_itens_opencv(quadro, itens, area, precisao):
    """Busca os templates no quadro, comparando somente os 65% superiores."""
    import cv2
    import numpy as np

    x1, y1, x2, y2 = area
    regiao = quadro[y1:y2, x1:x2]
    if regiao.size == 0:
        return []
    cinza_regiao = cv2.cvtColor(regiao, cv2.COLOR_BGR2GRAY)
    encontrados = []
    for item in itens:
        modelo = item["modelo"]
        altura_completa = item["altura"]
        largura_completa = item["largura"]
        altura_modelo, largura_modelo = modelo.shape[:2]
        if altura_modelo > cinza_regiao.shape[0] or largura_modelo > cinza_regiao.shape[1]:
            continue
        resultado = cv2.matchTemplate(
            cinza_regiao, modelo, cv2.TM_CCOEFF_NORMED
        )
        ys, xs = np.where(resultado >= precisao)
        candidatos = sorted(
            (
                (float(resultado[y, x]), int(x), int(y))
                for y, x in zip(ys.tolist(), xs.tolist())
            ),
            reverse=True,
        )
        aceitos = []
        for _, x, y in candidatos:
            # A comparação usa o recorte superior, mas o ícone inteiro deve
            # caber na região antes de permitir o clique central.
            if x + largura_completa > x2 - x1 or y + altura_completa > y2 - y1:
                continue
            if any(
                abs(x - anterior_x) < largura_modelo * 0.75
                and abs(y - anterior_y) < altura_modelo * 0.75
                for anterior_x, anterior_y in aceitos
            ):
                continue
            aceitos.append((x, y))
            encontrados.append(
                (x1 + x, y1 + y, largura_completa, altura_completa)
            )
    return encontrados


def carregar_dependencias_windows():
    """Importa e valida dependências que só existem no Windows."""
    try:
        import cv2
        import keyboard
        import numpy as np
        import win32con
        import win32gui
        import win32ui
    except ImportError as erro:
        raise ErroBot(
            "Dependência ausente. Execute criar_exe.bat ou instale os pacotes "
            "indicados no arquivo."
        ) from erro
    if os.name != "nt":
        raise ErroBot("Este bot depende de APIs do Windows (PrintWindow/PostMessage).")
    return cv2, keyboard, np, win32con, win32gui, win32ui


class JanelaJogo:
    def __init__(self, win32con, win32gui, win32ui, np):
        self.win32con = win32con
        self.win32gui = win32gui
        self.win32ui = win32ui
        self.np = np
        self.hwnd = self.localizar()

    def localizar(self):
        achadas = []

        def verificar(hwnd, _):
            try:
                if (
                    self.win32gui.IsWindowVisible(hwnd)
                    and NOME_JANELA.casefold()
                    in self.win32gui.GetWindowText(hwnd).casefold()
                ):
                    achadas.append(hwnd)
            except Exception:
                # Uma janela pode desaparecer durante a enumeração.
                return

        self.win32gui.EnumWindows(verificar, None)
        return achadas[0] if achadas else None

    def atualizar_handle(self):
        if self.hwnd is None or not self.win32gui.IsWindow(self.hwnd):
            self.hwnd = self.localizar()
        return self.hwnd

    def tamanho_cliente(self):
        hwnd = self.atualizar_handle()
        if hwnd is None:
            raise ErroBot("Não encontrei uma janela com 'otPokemon' no título.")
        if self.win32gui.IsIconic(hwnd):
            raise ErroBot("A janela do jogo está minimizada.")
        esquerda, topo, direita, baixo = self.win32gui.GetClientRect(hwnd)
        largura, altura = direita - esquerda, baixo - topo
        if largura <= 0 or altura <= 0:
            raise ErroBot("A janela do jogo não tem uma área cliente válida.")
        return largura, altura

    def capturar(self):
        hwnd = self.atualizar_handle()
        if hwnd is None:
            raise ErroBot("A janela do jogo não está disponível.")
        if self.win32gui.IsIconic(hwnd):
            raise ErroBot("A janela do jogo está minimizada.")
        esquerda, topo, direita, baixo = self.win32gui.GetWindowRect(hwnd)
        largura_janela, altura_janela = direita - esquerda, baixo - topo
        if largura_janela <= 0 or altura_janela <= 0:
            raise ErroBot("A janela do jogo tem dimensões inválidas.")

        dc_janela = self.win32gui.GetWindowDC(hwnd)
        dc_origem = self.win32ui.CreateDCFromHandle(dc_janela)
        dc_memoria = dc_origem.CreateCompatibleDC()
        bitmap = self.win32ui.CreateBitmap()
        try:
            bitmap.CreateCompatibleBitmap(dc_origem, largura_janela, altura_janela)
            dc_memoria.SelectObject(bitmap)
            resultado = self.win32gui.PrintWindow(
                hwnd, dc_memoria.GetSafeHdc(), 2
            )
            if resultado != 1:
                raise ErroBot(
                    "PrintWindow não conseguiu capturar o jogo. Alguns clientes "
                    "DirectX não permitem captura em segundo plano."
                )
            dados = bitmap.GetBitmapBits(True)
            imagem = self.np.frombuffer(dados, dtype=self.np.uint8)
            imagem = imagem.reshape((altura_janela, largura_janela, 4))[:, :, :3]

            cliente_esquerda, cliente_topo = self.win32gui.ClientToScreen(
                hwnd, (0, 0)
            )
            cliente_direita, cliente_baixo = self.win32gui.ClientToScreen(
                hwnd,
                self.win32gui.GetClientRect(hwnd)[2:],
            )
            cx = cliente_esquerda - esquerda
            cy = cliente_topo - topo
            largura_cliente = cliente_direita - cliente_esquerda
            altura_cliente = cliente_baixo - cliente_topo
            if (
                cx < 0
                or cy < 0
                or cx + largura_cliente > largura_janela
                or cy + altura_cliente > altura_janela
            ):
                raise ErroBot("Não foi possível alinhar a captura à área cliente.")
            return imagem[cy : cy + altura_cliente, cx : cx + largura_cliente].copy()
        finally:
            self.win32gui.DeleteObject(bitmap.GetHandle())
            dc_memoria.DeleteDC()
            dc_origem.DeleteDC()
            self.win32gui.ReleaseDC(hwnd, dc_janela)

    def clicar_direito(self, x, y):
        hwnd = self.atualizar_handle()
        if hwnd is None:
            raise ErroBot("A janela do jogo não está disponível para clicar.")
        largura, altura = self.tamanho_cliente()
        if not (0 <= x < largura and 0 <= y < altura):
            raise ErroBot("Clique recusado: coordenada fora da janela do jogo.")
        if self.win32gui.IsIconic(hwnd):
            raise ErroBot("Clique recusado: a janela do jogo está minimizada.")
        lparam = (int(y) << 16) | (int(x) & 0xFFFF)
        if not self.win32gui.PostMessage(
            hwnd, self.win32con.WM_RBUTTONDOWN, self.win32con.MK_RBUTTON, lparam
        ):
            raise ErroBot("O Windows recusou o clique direito (WM_RBUTTONDOWN).")
        if not self.win32gui.PostMessage(
            hwnd, self.win32con.WM_RBUTTONUP, 0, lparam
        ):
            raise ErroBot("O Windows recusou o clique direito (WM_RBUTTONUP).")


class Aplicativo:
    def __init__(self, raiz):
        self.raiz = raiz
        self.raiz.title("Bot de Loot - otPokemon")
        self.raiz.geometry("790x700")
        self.raiz.minsize(680, 600)
        self.raiz.configure(bg="#17191f")
        self.raiz.protocol("WM_DELETE_WINDOW", self.fechar)

        self.cv2 = self.keyboard = self.np = None
        self.win32con = self.win32gui = self.win32ui = None
        self.jogo = None
        self.ponto_corpo = None
        self.area_loot = None
        self.caminhos_itens = []
        self.evento_parar = threading.Event()
        self.evento_pausar = threading.Event()
        self.thread_motor = None
        self.fila_log = queue.Queue()
        self.var_estado = tk.StringVar(value="PARADO")
        self.var_jogo = tk.StringVar(value="Procurando janela do jogo...")
        self.var_precisao = tk.StringVar(value="0.85")
        self.var_intervalo = tk.StringVar(value="1.0")
        self._montar_interface()
        self._carregar_configuracao()
        self._iniciar_dependencias()
        self.raiz.after(150, self._processar_fila)
        self.raiz.after(1000, self._atualizar_status_jogo)

    def _montar_interface(self):
        estilo = ttk.Style()
        estilo.theme_use("clam")
        estilo.configure(
            "TButton", background="#303640", foreground="#f2f4f8",
            padding=8, borderwidth=0,
        )
        estilo.map("TButton", background=[("active", "#424b59")])
        estilo.configure(
            "TLabel", background="#17191f", foreground="#e7eaf0"
        )
        estilo.configure(
            "TFrame", background="#17191f"
        )

        conteudo = ttk.Frame(self.raiz, padding=16)
        conteudo.pack(fill="both", expand=True)
        ttk.Label(
            conteudo, text="BOT DE LOOT", font=("Segoe UI", 18, "bold")
        ).pack(anchor="w")
        barra = ttk.Frame(conteudo)
        barra.pack(fill="x", pady=(10, 4))
        ttk.Label(barra, text="Status:").pack(side="left")
        self.rotulo_estado = tk.Label(
            barra, textvariable=self.var_estado, bg="#3b414b",
            fg="#ffffff", padx=10, pady=4,
        )
        self.rotulo_estado.pack(side="left", padx=8)
        ttk.Label(barra, textvariable=self.var_jogo).pack(side="left", padx=8)

        cartoes = ttk.Frame(conteudo)
        cartoes.pack(fill="x", pady=12)
        for texto, comando in (
            ("Loot local", self.marcar_corpo),
            ("Loot area", self.marcar_area),
            ("Loot", self.escolher_itens),
            ("Limpar", self.limpar),
        ):
            ttk.Button(cartoes, text=texto, command=comando).pack(
                side="left", expand=True, fill="x", padx=(0, 7)
            )

        opcoes = ttk.Frame(conteudo)
        opcoes.pack(fill="x", pady=(2, 10))
        ttk.Label(opcoes, text="Precisão (0.50–1.00):").pack(side="left")
        ttk.Entry(opcoes, textvariable=self.var_precisao, width=8).pack(
            side="left", padx=(6, 18)
        )
        ttk.Label(opcoes, text="Intervalo (segundos):").pack(side="left")
        ttk.Entry(opcoes, textvariable=self.var_intervalo, width=8).pack(
            side="left", padx=6
        )

        botoes = ttk.Frame(conteudo)
        botoes.pack(fill="x", pady=(0, 10))
        ttk.Button(botoes, text="INICIAR", command=self.iniciar).pack(
            side="left", expand=True, fill="x", padx=(0, 7)
        )
        ttk.Button(botoes, text="PAUSAR", command=self.alternar_pausa).pack(
            side="left", expand=True, fill="x", padx=7
        )
        ttk.Button(botoes, text="PARAR", command=self.parar).pack(
            side="left", expand=True, fill="x", padx=(7, 0)
        )

        ttk.Label(conteudo, text="Itens selecionados (duplo clique remove):").pack(
            anchor="w"
        )
        quadro_lista = ttk.Frame(conteudo)
        quadro_lista.pack(fill="both", expand=True, pady=(5, 10))
        self.lista = tk.Listbox(
            quadro_lista, bg="#22262e", fg="#e7eaf0",
            selectbackground="#46556d", relief="flat",
        )
        barra_lista = ttk.Scrollbar(
            quadro_lista, orient="vertical", command=self.lista.yview
        )
        self.lista.configure(yscrollcommand=barra_lista.set)
        self.lista.pack(side="left", fill="both", expand=True)
        barra_lista.pack(side="right", fill="y")
        self.lista.bind("<Double-Button-1>", self.remover_item)

        ttk.Label(conteudo, text="Log:").pack(anchor="w")
        self.log = tk.Text(
            conteudo, height=8, bg="#111318", fg="#cbd2de",
            insertbackground="#ffffff", relief="flat", state="disabled",
            wrap="word",
        )
        self.log.pack(fill="x", pady=(5, 0))
        ttk.Label(
            conteudo,
            text="Teclas globais: HOME pausa/retoma | END para. "
                 "A área Loot area é recomendada para maior segurança.",
            foreground="#aeb7c5",
        ).pack(anchor="w", pady=(8, 0))

    def _iniciar_dependencias(self):
        try:
            (
                self.cv2, self.keyboard, self.np, self.win32con,
                self.win32gui, self.win32ui,
            ) = carregar_dependencias_windows()
            self.jogo = JanelaJogo(
                self.win32con, self.win32gui, self.win32ui, self.np
            )
            self.keyboard.add_hotkey("end", lambda: self.raiz.after(0, self.parar))
            self.keyboard.add_hotkey(
                "home", lambda: self.raiz.after(0, self.alternar_pausa)
            )
            self.registrar_log("Atalhos globais END e HOME ativados.")
        except Exception as erro:
            self.registrar_log(f"Dependências/janela indisponíveis: {erro}")

    def registrar_log(self, mensagem):
        self.fila_log.put(f"[{time.strftime('%H:%M:%S')}] {mensagem}")

    def _processar_fila(self):
        try:
            while True:
                mensagem = self.fila_log.get_nowait()
                if mensagem is None:
                    self._atualizar_estado_parado()
                    continue
                self.log.configure(state="normal")
                self.log.insert("end", mensagem + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        if self.raiz.winfo_exists():
            self.raiz.after(150, self._processar_fila)

    def _atualizar_status_jogo(self):
        encontrado = False
        if self.jogo:
            try:
                encontrado = self.jogo.atualizar_handle() is not None
            except Exception:
                encontrado = False
        self.var_jogo.set(
            "Jogo encontrado" if encontrado else "Jogo não encontrado"
        )
        if self.raiz.winfo_exists():
            self.raiz.after(1500, self._atualizar_status_jogo)

    def _abrir_seletor(self, instrucao, callback, quantidade=1):
        if not self.jogo:
            messagebox.showerror(
                "Janela do jogo", "Não foi possível inicializar as APIs do Windows."
            )
            return
        try:
            hwnd = self.jogo.atualizar_handle()
            if hwnd is None:
                raise ErroBot("Não encontrei uma janela com 'otPokemon' no título.")
            tamanho = self.jogo.tamanho_cliente()
        except Exception as erro:
            messagebox.showerror("Janela do jogo", str(erro))
            return

        overlay = tk.Toplevel(self.raiz)
        overlay.overrideredirect(True)
        overlay.attributes("-topmost", True)
        overlay.attributes("-alpha", 0.22)
        overlay.configure(bg="#10141c")
        largura_tela = overlay.winfo_screenwidth()
        altura_tela = overlay.winfo_screenheight()
        overlay.geometry(f"{largura_tela}x{altura_tela}+0+0")
        ttk.Label(
            overlay, text=instrucao, font=("Segoe UI", 16, "bold"),
            background="#10141c", foreground="#ffffff", padding=20,
        ).pack(anchor="n", pady=30)
        pontos = []

        def selecionar(evento):
            sx = overlay.winfo_rootx() + evento.x
            sy = overlay.winfo_rooty() + evento.y
            try:
                ponto = tuple(self.win32gui.ScreenToClient(hwnd, (sx, sy)))
            except Exception:
                overlay.destroy()
                messagebox.showerror("Seleção", "Não foi possível converter a posição.")
                return
            if not (0 <= ponto[0] < tamanho[0] and 0 <= ponto[1] < tamanho[1]):
                self.registrar_log(
                    "Seleção ignorada: clique fora da área cliente da janela do jogo."
                )
                return
            pontos.append(ponto)
            if len(pontos) < quantidade:
                return
            overlay.destroy()
            try:
                callback(pontos, tamanho)
            except Exception as erro:
                messagebox.showerror("Seleção", str(erro))

        overlay.bind("<Button-1>", selecionar)
        overlay.bind("<Escape>", lambda _evento: overlay.destroy())
        overlay.focus_force()

    def marcar_corpo(self):
        def concluido(pontos, _tamanho):
            self.ponto_corpo = pontos[0]
            self.registrar_log(f"Local do corpo salvo: {self.ponto_corpo}.")
            self._salvar_configuracao()

        self._abrir_seletor(
            "Clique no SQM onde os corpos caem (ESC cancela).", concluido
        )

    def marcar_area(self):
        def concluido(pontos, tamanho):
            x1, x2 = sorted((pontos[0][0], pontos[1][0]))
            y1, y2 = sorted((pontos[0][1], pontos[1][1]))
            if x2 - x1 < 8 or y2 - y1 < 8:
                raise ErroBot("A área marcada precisa ter pelo menos 8 x 8 pixels.")
            if x2 > tamanho[0] or y2 > tamanho[1]:
                raise ErroBot("A área marcada está fora da janela do jogo.")
            self.area_loot = (x1, y1, x2, y2)
            self.registrar_log(f"Área de loot salva: {self.area_loot}.")
            self._salvar_configuracao()

        self._abrir_seletor(
            "Clique em dois cantos da área das janelas de loot (ESC cancela).",
            concluido,
            quantidade=2,
        )

    def escolher_itens(self):
        caminhos = filedialog.askopenfilenames(
            title="Escolha os ícones dos itens",
            filetypes=[
                ("Imagens", "*.png *.bmp *.jpg *.jpeg"),
                ("Todos os arquivos", "*.*"),
            ],
        )
        adicionados = 0
        for caminho in caminhos:
            caminho = os.path.abspath(caminho)
            if caminho not in self.caminhos_itens:
                self.caminhos_itens.append(caminho)
                self.lista.insert("end", os.path.basename(caminho))
                adicionados += 1
        if adicionados:
            self.registrar_log(f"{adicionados} imagem(ns) de item adicionada(s).")
            self._salvar_configuracao()

    def remover_item(self, _evento=None):
        selecao = self.lista.curselection()
        if not selecao:
            return
        indice = selecao[0]
        self.lista.delete(indice)
        del self.caminhos_itens[indice]
        self._salvar_configuracao()
        self.registrar_log("Imagem de item removida.")

    def limpar(self):
        self.ponto_corpo = None
        self.area_loot = None
        self.caminhos_itens.clear()
        self.lista.delete(0, "end")
        self._salvar_configuracao()
        self.registrar_log("Posições e lista de itens limpas.")

    def _ler_opcoes(self):
        try:
            precisao = float(self.var_precisao.get())
            intervalo = float(self.var_intervalo.get())
        except ValueError as erro:
            raise ErroBot("Precisão e intervalo precisam ser números válidos.") from erro
        if not 0.50 <= precisao <= 1.00:
            raise ErroBot("A precisão deve estar entre 0.50 e 1.00.")
        if not 0.1 <= intervalo <= 60:
            raise ErroBot("O intervalo deve estar entre 0.1 e 60 segundos.")
        return precisao, intervalo

    def _carregar_modelos(self):
        modelos = []
        for caminho in self.caminhos_itens:
            imagem = self.cv2.imread(caminho, self.cv2.IMREAD_COLOR)
            if imagem is None or len(imagem.shape) < 2:
                raise ErroBot(f"Não foi possível abrir a imagem: {caminho}")
            altura, largura = imagem.shape[:2]
            altura_recorte = max(1, int(altura * ALTURA_MODELO))
            recorte = imagem[:altura_recorte, :]
            modelo = self.cv2.cvtColor(recorte, self.cv2.COLOR_BGR2GRAY)
            if modelo.size == 0:
                raise ErroBot(f"A imagem do item está vazia: {caminho}")
            modelos.append(
                {
                    "caminho": caminho,
                    "modelo": modelo,
                    "largura": largura,
                    "altura": altura,
                }
            )
        return modelos

    def iniciar(self):
        if self.thread_motor and self.thread_motor.is_alive():
            self.registrar_log("O motor já está em execução.")
            return
        if not self.jogo or not self.ponto_corpo:
            messagebox.showwarning(
                "Configuração", "Encontre o jogo e marque o Loot local primeiro."
            )
            return
        if not self.caminhos_itens:
            messagebox.showwarning("Configuração", "Adicione ao menos um ícone de item.")
            return
        try:
            precisao, intervalo = self._ler_opcoes()
            modelos = self._carregar_modelos()
            tamanho = self.jogo.tamanho_cliente()
            self._validar_configuracao(tamanho)
        except Exception as erro:
            messagebox.showerror("Não foi possível iniciar", str(erro))
            return

        self.evento_parar.clear()
        self.evento_pausar.clear()
        self.thread_motor = threading.Thread(
            target=self._executar_motor,
            args=(tamanho, modelos, precisao, intervalo),
            daemon=True,
        )
        self.thread_motor.start()
        self.var_estado.set("RODANDO")
        self.rotulo_estado.configure(bg="#246c48")
        self.registrar_log("Motor iniciado.")

    def _validar_configuracao(self, tamanho):
        largura, altura = tamanho
        x, y = self.ponto_corpo
        if not (0 <= x < largura and 0 <= y < altura):
            raise ErroBot("O ponto do corpo está fora da janela atual; marque novamente.")
        if self.area_loot:
            x1, y1, x2, y2 = self.area_loot
            if not (0 <= x1 < x2 <= largura and 0 <= y1 < y2 <= altura):
                raise ErroBot("A área de loot está fora da janela atual; marque novamente.")

    def _executar_motor(self, tamanho, modelos, precisao, intervalo):
        try:
            motor = MotorLoot(
                tamanho_cliente=tamanho,
                ponto_corpo=self.ponto_corpo,
                area_loot=self.area_loot,
                itens=modelos,
                precisao=precisao,
                capturar=self.jogo.capturar,
                clicar=self.jogo.clicar_direito,
                localizar=localizar_itens_opencv,
                obter_tamanho=self.jogo.tamanho_cliente,
            )
            if self.area_loot is None:
                self.registrar_log(
                    "Loot area não marcada: usando região segura de até "
                    "320 x 240 px ancorada no Loot local."
                )
            while not self.evento_parar.is_set():
                if self.evento_pausar.is_set():
                    self.evento_parar.wait(0.1)
                    continue
                quantidade = motor.executar_ciclo()
                if quantidade:
                    self.registrar_log(f"{quantidade} clique(s) em item(ns) encontrado(s).")
                self.evento_parar.wait(intervalo)
        except Exception as erro:
            self.registrar_log(f"Motor interrompido: {erro}")
            self.registrar_log(traceback.format_exc().strip().splitlines()[-1])
            self.evento_parar.set()
        finally:
            self.fila_log.put(None)

    def _atualizar_estado_parado(self):
        if self.var_estado.get() != "PARADO":
            self.var_estado.set("PARADO")
            self.rotulo_estado.configure(bg="#3b414b")
            self.registrar_log("Motor parado.")

    def alternar_pausa(self):
        if not self.thread_motor or not self.thread_motor.is_alive():
            self.registrar_log("O motor não está em execução.")
            return
        if self.evento_pausar.is_set():
            self.evento_pausar.clear()
            self.var_estado.set("RODANDO")
            self.rotulo_estado.configure(bg="#246c48")
            self.registrar_log("Motor retomado.")
        else:
            self.evento_pausar.set()
            self.var_estado.set("PAUSADO")
            self.rotulo_estado.configure(bg="#8a6720")
            self.registrar_log("Motor pausado.")

    def parar(self):
        self.evento_parar.set()
        self.evento_pausar.clear()
        if self.thread_motor and self.thread_motor.is_alive():
            self.var_estado.set("PARADO")
            self.rotulo_estado.configure(bg="#3b414b")
            self.registrar_log("Solicitada parada do motor.")

    def _caminho_config(self):
        return os.path.join(pasta_programa(), ARQUIVO_CONFIG)

    def _salvar_configuracao(self):
        dados = {
            "ponto_corpo": list(self.ponto_corpo) if self.ponto_corpo else None,
            "area_loot": list(self.area_loot) if self.area_loot else None,
            "itens": self.caminhos_itens,
            "precisao": self.var_precisao.get(),
            "intervalo": self.var_intervalo.get(),
        }
        destino = self._caminho_config()
        temporario = destino + ".tmp"
        try:
            with open(temporario, "w", encoding="utf-8") as arquivo:
                json.dump(dados, arquivo, ensure_ascii=False, indent=2)
            os.replace(temporario, destino)
        except OSError as erro:
            self.registrar_log(f"Não foi possível salvar a configuração: {erro}")
            try:
                if os.path.exists(temporario):
                    os.remove(temporario)
            except OSError:
                pass

    def _carregar_configuracao(self):
        caminho = self._caminho_config()
        if not os.path.isfile(caminho):
            return
        try:
            with open(caminho, "r", encoding="utf-8") as arquivo:
                dados = json.load(arquivo)
            if not isinstance(dados, dict):
                raise ValueError("o conteúdo principal precisa ser um objeto JSON")
            ponto = dados.get("ponto_corpo")
            if (
                isinstance(ponto, list)
                and len(ponto) == 2
                and all(type(valor) is int and valor >= 0 for valor in ponto)
            ):
                self.ponto_corpo = tuple(ponto)
            area = dados.get("area_loot")
            if (
                isinstance(area, list)
                and len(area) == 4
                and all(type(valor) is int and valor >= 0 for valor in area)
                and area[0] < area[2]
                and area[1] < area[3]
            ):
                self.area_loot = tuple(area)
            itens = dados.get("itens", [])
            if isinstance(itens, list):
                for item in itens:
                    if isinstance(item, str) and os.path.isfile(item):
                        caminho_item = os.path.abspath(item)
                        self.caminhos_itens.append(caminho_item)
                        self.lista.insert("end", os.path.basename(caminho_item))
            precisao = str(dados.get("precisao", "0.85"))
            intervalo = str(dados.get("intervalo", "1.0"))
            self.var_precisao.set(precisao[:20])
            self.var_intervalo.set(intervalo[:20])
            self.registrar_log("Última configuração carregada.")
        except (OSError, ValueError, TypeError, json.JSONDecodeError) as erro:
            self.registrar_log(f"Configuração não carregada: {erro}")

    def fechar(self):
        self.parar()
        if self.keyboard:
            try:
                self.keyboard.unhook_all_hotkeys()
            except Exception:
                pass
        self.raiz.destroy()


def main():
    raiz = tk.Tk()
    Aplicativo(raiz)
    raiz.mainloop()


if __name__ == "__main__":
    main()
