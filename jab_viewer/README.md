JABViewer
=========

Aplicação de inspeção para aplicações Java via Java Access Bridge (JAB),
construída com Python, CustomTkinter e java-access-bridge-wrapper.

Pré‑requisitos
--------------
- Windows 10+
- Python 3.9+
- Java Access Bridge habilitado (JRE/JDK 64‑bit)
- DLL `WindowsAccessBridge-64.dll` acessível e variável de ambiente
  `RC_JAVA_ACCESS_BRIDGE_DLL` apontando para ela.

Instalação
----------
- Requisitos Python:

  pip install -r requirements.txt

- Se a variável `RC_JAVA_ACCESS_BRIDGE_DLL` não estiver definida, informe o
  caminho da DLL na primeira execução quando solicitado, ou crie um arquivo
  `.env` em `jab_viewer/.env` com a linha:

  RC_JAVA_ACCESS_BRIDGE_DLL=C:\\Program Files\\Java\\jdk-17\\bin\\WindowsAccessBridge-64.dll

Execução
--------

  python -m jab_viewer.app

Funcionalidades
---------------
- Lista de janelas Java ativas (dropdown) e botão de recarregar.
- Seleção de aplicação coloca a janela Java em primeiro plano e mantém o
  JABViewer sempre no topo.
- Árvore de elementos (Accessibility Context) da aplicação.
- Ao clicar em um elemento: highlight com borda vermelha e painel de
  propriedades detalhado.

