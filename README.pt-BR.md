# agent-batch

🌐 Idiomas: [🇺🇸 English](README.md) | [🇧🇷 Português (Brasil)](README.pt-BR.md)

Executa lotes de prompts em janelas ou painéis do tmux, ou como sessões do [agent-manager](https://github.com/YoanWai/agent-manager). Requer Python 3.11+, tmux e as CLIs das IAs que você pretende usar. Usa o shell interativo de `$SHELL`, incluindo funções e aliases (bash, zsh ou outro shell POSIX).

## Instalação local

Na raiz do projeto, crie um link para o executável em um diretório do PATH:

```sh
mkdir -p "$HOME/.bin"
ln -s "$PWD/agent-batch" "$HOME/.bin/agent-batch"
```

O diretório `~/.bin` deve estar no PATH. O link acompanha as alterações no projeto sem precisar copiar o script novamente. A configuração pessoal fica fora do projeto, em `~/.config/agent-batch/config.toml` (ou no diretório indicado por `XDG_CONFIG_HOME`).

## Uso

```sh
agent-batch 'Revise {{PR_URL}} considerando {{TYPE}}' \
  --agent claude --path ~/projetos/app \
  --item PR_URL=https://github.com/org/repo/pull/123 TYPE=backend TITLE='PR 123' \
  --item PR_URL=https://github.com/org/repo/pull/124 TYPE=frontend
```

Cada `--item` define uma execução. As chaves ignoram maiúsculas/minúsculas. `TITLE` nomeia a janela/painel; sem ele, os nomes são `task-1`, `task-2` etc. Use `--prefix` para mudar esse prefixo. `AGENT` executa um item com outra instância de IA (veja [Agente por item](#agente-por-item)), e `PATH` o executa em outro diretório (veja [Diretório por item](#diretório-por-item)). `--template arquivo.txt` substitui o prompt passado como texto. `--dry-run` mostra os prompts sem iniciar as IAs. `--var` define valores compartilhados por todos os itens (veja [Variáveis compartilhadas](#variáveis-compartilhadas)), e `--items` lista valores soltos quando só uma chave varia (veja [Um valor por item](#um-valor-por-item)).

### Variáveis compartilhadas

Use `--var` para valores iguais em todos os itens, em vez de repeti-los em cada `--item`. O valor definido no próprio item tem prioridade; assim, `--var` também funciona como padrão:

```sh
agent-batch 'Revise {{PR_URL}} em {{REPO}} considerando {{TYPE}}' \
  --var REPO=org/repo TYPE=backend \
  --item PR_URL=https://github.com/org/repo/pull/123 \
  --item PR_URL=https://github.com/org/repo/pull/124 TYPE=frontend
```

Os dois itens usam `REPO=org/repo`; o primeiro usa `TYPE=backend`, e o segundo o substitui por `frontend`. Os valores compartilhados também preenchem `{{CHAVE}}` em `--title` e `--session-name` e são literais, como os valores de item. Liste vários pares após `--var` ou repita a opção. Assim como `--item`, ela consome todos os argumentos seguintes; por isso, escreva o prompt antes dela. `AGENT`, `PATH`, `TITLE` e `SESSION_NAME` não podem ser compartilhados; use `--agent`, `--path`, `--title` e `--session-name`. Sem `--item`, o prompt roda uma vez com os valores compartilhados.

### Um valor por item

Quando só uma chave muda entre os itens, `--items` recebe os valores soltos, em vez de repetir `--item CHAVE=VALOR`:

```sh
agent-batch --template review-pr.md --title 'PR {{PR}}' \
  --var REPO=org/repo \
  --items 123 124 125
```

Isso equivale a `--item PR=123 --item PR=124 --item PR=125`. A chave é a única do prompt, de `--title` e de `--session-name` sem valor em `--var`; `{{AGENT}}` nunca conta. Se não sobrar nenhuma chave ou sobrar mais de uma, nada é iniciado e o erro lista as chaves: defina todas menos uma com `--var` ou use `--item`. Os valores são literais e podem conter `=`, mas um valor que começa com a própria chave (`PR=123`) é rejeitado, por provavelmente ser um `--item` digitado errado. `--items` não pode ser combinado com `--item` nem com o modo interativo. Assim como `--item`, a opção consome todos os argumentos seguintes; por isso, escreva o prompt antes dela.

### Modo interativo e histórico

Execute `agent-batch` sem argumentos em um terminal para escolher um prompt salvo ou criar outro. Também é possível começar com um prompt ou arquivo específico: `agent-batch -i 'Revise {{PR_URL}}'` ou `agent-batch -i --template review.txt`. O programa pergunta o valor de cada marcador `{{CHAVE}}` e mostra o prompt montado. No mesmo menu, você pode adicionar outro item, editar o prompt, definir um título específico com `t`, executar aquele item com outra instância de IA com `g` ou em outro diretório com `p`, refazer o item ou terminar e iniciar o lote. Sem essa escolha, o título vem de `--title` ou do padrão `task-1`, `task-2` etc. `--agent`, `--path`, `--layout`, `--var`, `--detach` e `--dry-run` continuam disponíveis nesse modo; as chaves compartilhadas não são perguntadas.

O agente do lote, o caminho, o layout e as variáveis compartilhadas aparecem logo na abertura, sem uma pergunta adicional. Para alterá-los, cancele com `Ctrl-C` e execute novamente usando as opções indicadas. As mensagens exibidas pelo CLI são em inglês; escolher `finish and launch` na prévia do último item inicia o lote, sem outra confirmação.

Ao criar um prompt no terminal, termine a entrada com uma linha contendo apenas `.`. Para buscar no histórico, digite `/texto` na escolha do prompt. O histórico guarda os **modelos**, sem os valores preenchidos, em `~/.config/agent-batch/history.json` (ou `$XDG_CONFIG_HOME/agent-batch/history.json`). Execuções feitas com os argumentos tradicionais também alimentam esse histórico; `--dry-run` não o altera. O arquivo fica fora do repositório.

Na prévia de um item, escolha `e` para editar o modelo no editor indicado por `$VISUAL` ou `$EDITOR` (padrão: `vi`). Se você adicionar `{{ISSUE_URL}}` ao preencher o quarto item, o programa pergunta o valor dessa nova chave e preserva os valores já informados para o item. Os três itens anteriores mantêm seus prompts originais; a edição vale para o item atual e os seguintes. Escolha `r` para refazer os valores do item atual.

### Títulos de janela e nomes de sessão

`TITLE` nomeia a janela/painel do tmux. `SESSION_NAME` nomeia a própria sessão da IA (no Claude, `claude --name`, exibido na caixa de prompt, no seletor do `/resume` e no título do terminal). Ambos são chaves do item, e seus valores são literais, como todo valor de item.

Para montar esses nomes a partir das variáveis do item, use os modelos do lote `--title` e `--session-name`. Eles aceitam marcadores `{{CHAVE}}` e são renderizados para cada item, assim como o prompt. `TITLE` ou `SESSION_NAME` definidos no item têm prioridade sobre o modelo:

```sh
agent-batch 'Revise {{PR_URL}}' --title 'PR {{PR}}' --session-name 'review {{PR}}' \
  --item PR=123 PR_URL=https://github.com/org/repo/pull/123 \
  --item PR=124 PR_URL=https://github.com/org/repo/pull/124 SESSION_NAME=urgente
```

Sem `TITLE` nem `--title`, as janelas se chamam `PREFIXO-1`, `PREFIXO-2` etc. Sem `SESSION_NAME` nem `--session-name`, a IA usa o nome de sessão padrão dela. O Codex não aceita nome de sessão pela linha de comando (apenas `/rename` dentro da sessão); por isso, um nome de sessão em um item que usa uma instância `codex` é rejeitado antes de iniciar qualquer coisa.

O padrão é uma janela por execução (`--layout window`). Para painéis na mesma janela, use `--layout pane`, com `--pane-layout even-horizontal` (lado a lado), `even-vertical` (empilhados) ou `tiled` (grade). Dentro do tmux, usa a sessão atual; fora, cria e abre uma nova sessão. `--detach` cria as execuções sem abrir a sessão nem mudar seu foco.

### Agente por item

`--agent` (ou `default_agent` na configuração) define o agente do lote. A chave de item `AGENT` executa apenas aquele item com outra instância. `{{AGENT}}` sempre é renderizado com o nome da instância do item no prompt, em `--title` e em `--session-name`; por isso, nunca é perguntado nem acusado como ausente. Assim, cada item pode escrever em um arquivo próprio:

```sh
agent-batch 'Revise {{PR_URL}} e escreva as conclusões em reviews/{{PR}}-{{AGENT}}.md' \
  --agent claude --title 'PR {{PR}} ({{AGENT}})' \
  --item PR=123 PR_URL=https://github.com/org/repo/pull/123 \
  --item PR=123 PR_URL=https://github.com/org/repo/pull/123 AGENT=codex \
  --item PR=124 PR_URL=https://github.com/org/repo/pull/124
```

O primeiro e o terceiro itens executam `claude` e escrevem `reviews/123-claude.md` e `reviews/124-claude.md`; o segundo executa `codex` e escreve `reviews/123-codex.md`. `AGENT` deve nomear uma instância disponível (veja `--list-agents`). No `--dry-run`, itens cujo agente difere do agente do lote aparecem marcados com `· agent: NOME`.

### Diretório por item

`--path` define o diretório do lote (padrão: o diretório atual). A chave de item `PATH` executa apenas aquele item em outro diretório; assim, cada agente já abre dentro do próprio repositório e carrega os arquivos de projeto dele (no Claude, `CLAUDE.md` e `.claude/`). Um `PATH` relativo é resolvido a partir de `--path`; `~` e caminhos absolutos são usados como estão:

```sh
agent-batch --template review.md --path ~/projetos --title '{{PATH}} #{{PR}}' \
  --item PATH=api PR=12 \
  --item PATH=web PR=34 \
  --item PATH=~/trabalho/site PR=56
```

Os itens rodam em `~/projetos/api`, `~/projetos/web` e `~/trabalho/site`. Todos os diretórios precisam existir; caso contrário, nada é iniciado. Assim como `TITLE`, `{{PATH}}` é renderizado com o valor literal do item e só é exigido onde um modelo o usa. No `--dry-run`, itens cujo diretório difere do diretório do lote aparecem marcados com `· path: DIRETÓRIO`.

### agent-manager

Com `--backend agent-manager`, cada item vira uma sessão do [agent-manager](https://github.com/YoanWai/agent-manager) em vez de uma janela do tmux; assim, o lote aparece na lista do agent-manager, com status ao vivo, revive e revisão de diff. Modelos, `--var`, `AGENT`, `PATH`, histórico, modo interativo e `--dry-run` funcionam normalmente:

```sh
agent-batch 'Revise {{PR_URL}}' --backend agent-manager --agent claude \
  --path ~/projetos/api --title 'PR {{PR}}' \
  --item PR=12 PR_URL=https://github.com/org/repo/pull/12 \
  --item PR=13 PR_URL=https://github.com/org/repo/pull/13
```

Cada item executa `agent-manager spawn --tool TIPO --directory DIRETÓRIO --name TÍTULO --prompt PROMPT`. O título (`TITLE`, `--title` ou `PREFIXO-N`) nomeia a sessão no agent-manager, inclusive no Codex. O agent-manager não repassa um nome de sessão para a IA; por isso, `SESSION_NAME` e `--session-name` são rejeitados, e `--layout` e `--pane-layout` não se aplicam. As sessões ficam no grupo raiz do agent-manager (ou no grupo da sessão que chamou, quando executado dentro do agent-manager).

O agent-manager inicia os próprios `claude` e `codex` embutidos, com o ambiente do servidor tmux dele, e não o do seu shell. Só funcionam instâncias cujo comando é apenas o nome do tipo (as embutidas `claude` e `codex`); uma instância baseada em função do shell, alias ou argumentos fixos, como `claude-work`, é rejeitada antes de qualquer sessão ser criada. Os itens são criados em ordem; se o agent-manager falhar em um deles, o lote para e informa quantas sessões já foram criadas.

## Tipos e instâncias de IA

Um **tipo** define como invocar uma CLI e entregar o prompt. Os tipos suportados no código são `claude` e `codex`. Uma **instância** dá um nome a um comando de um desses tipos: outro perfil, executável, função ou alias do shell.

Sem configuração, existem as instâncias `claude` e `codex`, e `claude` é o padrão. O arquivo opcional é `~/.config/agent-batch/config.toml`; se `XDG_CONFIG_HOME` estiver definido, é `$XDG_CONFIG_HOME/agent-batch/config.toml`. Use `--config ARQUIVO` para selecionar outro arquivo. O arquivo explícito substitui a configuração pessoal; ambos sempre partem das instâncias embutidas.

```toml
default_agent = "claude-work"

[agents.claude-work]
type = "claude"
command = ["claude-work"]

[agents.codex-work]
type = "codex"
command = ["codex", "--profile", "work"]
```

`type` é obrigatório. `command` é uma lista: o primeiro elemento é o comando, e os demais são argumentos fixos. Se omitido, usa o nome da instância como comando. Os argumentos são passados literalmente; não há expansão de `$VAR`, `~`, pipelines ou interpolação de prompts na configuração. Use caminhos absolutos quando precisar indicar um executável fora do PATH. O adaptador do tipo acrescenta o prompt depois dos argumentos fixos.

Instâncias configuradas são adicionadas às embutidas; usar o mesmo nome substitui aquela instância. `--agent NOME` tem prioridade sobre `default_agent`. Erros de configuração e tipos desconhecidos são rejeitados antes de criar janelas ou iniciar IAs.

```sh
agent-batch --list-agents
agent-batch --agent claude-work 'Explique este projeto'
agent-batch --config examples/agent-batch.config.toml --list-agents
```

Para adicionar um **novo tipo de IA**, implemente um adaptador que receba `(command, prompt, session_name=None)` e retorne a lista de argumentos, registre-o em `AGENT_TYPES` e inclua testes para o formato de invocação. Se a CLI não permitir definir o nome da sessão na inicialização, lance `ValueError` quando `session_name` for informado. Uma nova instância de um tipo já suportado requer apenas configuração.

## Testes

```sh
python3 -m unittest discover -s tests -v
```

Os testes de integração usam servidores tmux isolados e CLIs simuladas.
