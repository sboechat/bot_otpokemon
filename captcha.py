import pyautogui as pg
import time
from PIL import Image
import threading

lock = threading.Lock()
SIZE_X, SIZE_Y = pg.size()
X = SIZE_X / 1920
Y = SIZE_Y / 1080

IMG_SUPERIOR = [(int(X*892), int(Y*503)), (int(X*957),int(Y*504)), (int(X*1029),int(Y*502))]
IMG_INFERIOR = [(int(X*892), int(Y*563)), (int(X*957), int(Y*564)), (int(X*1029), int(Y*562))]
DESAFIO_REGIAO = (int(X*851), int(Y*528), int(X*218), int(Y*73))
BOTAO_CONFIRMAR = (int(X*1009), int(Y*616))
BOTAO_APAGAR = (int(X*908), int(Y*618))
POS_PAUSE_PESCA = (int(X*714), int(Y*117))
CLICANDO = False
LIGADO = True
RESOLVENDO = False
def is_resolvendo():
    return RESOLVENDO

def is_clicando():
    return CLICANDO

def tirar_foto(posicao):
    x, y = posicao
    foto = pg.screenshot(region=(int(x - X*32), int(y - Y*31), int(X*62), int(Y*56))) # TENHO QUE CALCULAR MELHOR O TAMANHO DO PRINT DO POKEMON
    return foto

def rotacionar_foto(imagem, grau):
    # print(grau, ' GRAUS')
    imagem_rotacionada = imagem.rotate(grau, Image.BICUBIC)
    return imagem_rotacionada

def procurar_imagem(caminho_da_imagem, my_confidence, my_region=None, grayscale = False):
    try:
        box = pg.locateOnScreen(caminho_da_imagem, confidence=my_confidence, region=my_region, grayscale=grayscale)
        if box:
            return box
    except:
        pass
    return None

def is_captcha():
    return procurar_imagem('imgs/inicio_captcha.png', 0.8)

def ligar_captcha():
    global LIGADO
    LIGADO = True
    procurar_captcha()

def desligar_captcha():
    global LIGADO
    LIGADO = False    

def resolver_captcha():
    imagem_encontrada = []
    imagem_nao_encontrada = []
    threads = {}
    confidence_start = 0.95
    confidence_end = confidence_start - 0.11
    for posicao in IMG_SUPERIOR:
        threads[f'procurar_par_captcha_thread_{posicao}'] =(threading.Thread(target=procurar_par_captcha_thread, args=(posicao, imagem_encontrada, imagem_nao_encontrada, confidence_start, confidence_end)))
    
    for t in threads.copy():
        if t in threads and not threads[t].is_alive():
            threads[t].start()

    for t in threads.copy():
        if t in threads:
            threads[t].join()

    len_nao_encontradas = len(imagem_nao_encontrada)
    len_encontradas = len(imagem_encontrada)
    while len_nao_encontradas > 1:
        confidence_start = confidence_end
        confidence_end = confidence_start - 0.11
        if confidence_end < 0:
            break
        for posicao in imagem_nao_encontrada.copy():
            imagem_encontrada, imagem_nao_encontrada = procurar_par_captcha_thread(posicao, imagem_encontrada, imagem_nao_encontrada, confidence_start, confidence_end)
            if len_encontradas < len(imagem_encontrada):
                len_encontradas = len(imagem_encontrada)
                imagem_nao_encontrada.remove(posicao)
                len_nao_encontradas = len(imagem_nao_encontrada)
                if len_encontradas > 1:
                    return (imagem_encontrada, imagem_nao_encontrada)


    return (imagem_encontrada, imagem_nao_encontrada)

def procurar_par_captcha_thread(posicao, imagem_encontrada=[], imagem_nao_encontrada=[], confidence_start = 0.95, confidence_end = 0.69):
    imagem_carregada = tirar_foto(posicao)
    confidence = confidence_start
    box = False

    while not box:
        if confidence < confidence_end:
            lock.acquire()
            imagem_nao_encontrada.append(posicao)
            lock.release()
            return (imagem_encontrada, imagem_nao_encontrada)
        for grau in range(0, 360, 10):
            imagem_rotacionada = rotacionar_foto(imagem_carregada, grau)
            try:
                box = pg.locateOnScreen(imagem_rotacionada, confidence=confidence, region=DESAFIO_REGIAO)
                if box:
                    print('BOX - IMAGEM ENCONTRADA - ', box, confidence)
                    x, y = pg.center(box)
                    lock.acquire()
                    imagem_encontrada.append([posicao, (x, y)])
                    lock.release()
                    return (imagem_encontrada, imagem_nao_encontrada)
            except:
                pass
        confidence = confidence - 0.05

def desbugar_click():
    try:
        pg.moveTo(IMG_SUPERIOR[0], duration=0.3)
        pg.click()
        pg.moveTo(IMG_INFERIOR[0], duration=0.3)
        pg.click()
        pg.moveTo(BOTAO_APAGAR, duration=0.3)
        pg.click()
    except:
        pass

def resolver_captcha_thread():
    global CLICANDO, RESOLVENDO
    RESOLVENDO = True
    inicio = time.time()
    CLICANDO = True
    pg.sleep(1.5)
    desbugar_click()
    CLICANDO = False
    pg.screenshot(imageFilename=f"./imgs/captcha/captcha_{int(time.time())}.png")
    imagem_encontrada, imagem_nao_encontrada = resolver_captcha()
    fim = time.time()
    print(f"Tempo para encontrar as imagens: {fim - inicio}")
    
    CLICANDO = True
    pg.sleep(3)
    desbugar_click()
    #clicar no captcha
    for posicao in imagem_encontrada:
        pg.moveTo(posicao[0], duration=0.2)
        pg.click()
        pg.moveTo(posicao[1], duration=0.2)
        pg.click()
    for posicao in imagem_nao_encontrada:
        pg.moveTo(posicao, duration=0.2)
        pg.click()
        for tentativa in IMG_INFERIOR:
            pg.moveTo(tentativa, duration=0.2)
            pg.click()
    pg.moveTo(BOTAO_CONFIRMAR, duration=0.2)
    pg.click()
    pg.sleep(0.5)
    CLICANDO = False
    RESOLVENDO = False
    fim = time.time()
    print(f"Tempo para resolver: {fim - inicio}")
    print(f"Imagens encontradas: {len(imagem_encontrada)} / imagens não encontradas: {len(imagem_nao_encontrada)}")

def procurar_captcha():
    global RESOLVENDO
    if not RESOLVENDO and is_captcha():
        threading.Thread(target=resolver_captcha_thread).start()
        
if __name__ == "__main__":
    procurar_captcha()

