# agent-batch

🌐 Idiomas: [🇺🇸 English](README.md) | [🇧🇷 Português (Brasil)](README.pt-BR.md)

Executa lotes de prompts em janelas ou painéis do tmux. Requer Python 3.11+, tmux e as CLIs das IAs que você pretende usar. Usa o shell interativo de `$SHELL`, incluindo funções e aliases (bash, zsh ou outro shell POSIX).

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

Cada `--item` define uma execução. As chaves ignoram maiúsculas/minúsculas. `TITLE` nomeia a janela/painel; sem ele, os nomes são `task-1`, `task-2` etc. Use `--prefix` para mudar esse prefixo. `--template arquivo.txt` substitui o prompt passado como texto. `--dry-run` mostra os prompts sem iniciar as IAs.

### Modo interativo e histórico

Execute `agent-batch` sem argumentos em um terminal para escolher um prompt salvo ou criar outro. Também é possível começar com um prompt ou arquivo específico: `agent-batch -i 'Revise {{PR_URL}}'` ou `agent-batch -i --template review.txt`. O programa pergunta o valor de cada marcador `{{CHAVE}}` e mostra o prompt montado. No mesmo menu, você pode adicionar outro item, editar o prompt, definir um título específico com `t`, refazer o item ou terminar e iniciar o lote. Sem essa escolha, o título vem de `--title` ou do padrão `task-1`, `task-2` etc. `--agent`, `--path`, `--layout`, `--detach` e `--dry-run` continuam disponíveis nesse modo.

O agente, o caminho e o layout aparecem logo na abertura, sem uma pergunta adicional. Para alterá-los, cancele com `Ctrl-C` e execute novamente usando as opções indicadas. As mensagens exibidas pelo CLI são em inglês; escolher `finish and launch` na prévia do último item inicia o lote, sem outra confirmação.

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

Sem `TITLE` nem `--title`, as janelas se chamam `PREFIXO-1`, `PREFIXO-2` etc. Sem `SESSION_NAME` nem `--session-name`, a IA usa o nome de sessão padrão dela. O Codex não aceita nome de sessão pela linha de comando (apenas `/rename` dentro da sessão); por isso, um nome de sessão com uma instância `codex` é rejeitado antes de iniciar qualquer coisa.

O padrão é uma janela por execução (`--layout window`). Para painéis na mesma janela, use `--layout pane`, com `--pane-layout even-horizontal` (lado a lado), `even-vertical` (empilhados) ou `tiled` (grade). Dentro do tmux, usa a sessão atual; fora, cria e abre uma nova sessão. `--detach` cria as execuções sem abrir a sessão nem mudar seu foco.

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
