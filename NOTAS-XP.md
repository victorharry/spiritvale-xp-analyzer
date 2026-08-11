# Como o jogo manda XP, e o que dá pra concluir disso

Anotações da engenharia reversa em cima de captura real. Estão aqui porque
nenhuma delas é dedutível do código — todas vieram de olhar o tráfego.

## O que o servidor manda

No `CharacterData` (RPCs `LoadCharacter_T` e `CharacterCallback_T`):

```
level          nível de classe
experience     XP absoluto DENTRO do nível
jobLevel       nível de job
jobExperience  XP de job, também dentro do nível
```

**Não existe campo dizendo quanto o nível pede.** Essa é a limitação central de
tudo o que vem depois: XP de 12,7 milhões pode ser 30% ou 95% do nível.

Duas confirmações de que o XP é *dentro* do nível, não acumulado:

1. Um job no nível 70 (o máximo) reporta `jobExperience = 0`. Se fosse
   acumulado desde o nível 1, seria um número enorme.
2. Captura do personagem Corujo do nível 1 ao 12: o XP zera a cada subida.

## Quando ele manda

Não é contínuo. Numa janela de 60s parado, **nenhum** `CharacterData` passou.
Ele chega no login e quando o progresso muda. Uma sonda que conclui "não achei
nada" com o personagem parado está certa sobre o que viu e errada sobre o
motivo.

## Descobrindo o tamanho do nível

Duas fontes, com forças opostas.

### Pelo level up (só rede, sem tela)

O maior XP visto antes da virada é aproximadamente o que o nível pedia. O erro
é de uma morte de mob — o que dá em porcentagem depende do nível:

| nível | XP do nível | erro típico |
|---|---|---|
| 1 | 27 | 2178% |
| 5 | 1.568 | 37% |
| 11 | 8.585 | 6,8% |
| 114 | ~13.000.000 | **0,25%** |

Medido com ganho mediano de 588 XP por leitura no Corujo (níveis 1–12) e
~33.000 por leitura no Galinho (nível 114).

Ou seja: inútil em nível baixo, ótimo em nível alto — e é em nível alto que a
estimativa de tempo interessa. **Não extrapole uma curva a partir dos níveis
1–12**: os limites observados são frouxos demais e as razões entre níveis
consecutivos deram de 0,80 a 2,51, sem forma fechada confiável.

### Pela barra na memória (atalho)

`necessário = xp ÷ porcentagem`. Serve pra ter estimativa no nível em que você
já está, sem esperar subir de nível.

Só que a detecção da barra por comportamento é fraca: ela descarta candidatos
que *descem*, e valor estático nunca desce — sobram ~1.700. Por isso o
aprendizado exige XPs **diferentes** e estimativas que concordem em 5%: só a
barra certa mantém `xp ÷ preenchimento` constante enquanto o XP sobe. Barra
errada não ensina nada, em vez de ensinar besteira.

**Melhoria óbvia ainda não feita:** aplicar esse mesmo teste de razão nos ~1.700
candidatos de uma vez, em vez de escolher um pelo filtro fraco e validar
depois. A barra certa é a única com razão estável em duas ou três subidas de
XP — acharia em segundos e com certeza.

## Achando o CharacterData no pacote

A caçada tenta decodificar a partir de cada posição plausível, em vez de
resolver o protocolo. O que impede isso de virar chute:

- seis strings utf-8 válidas dentro do limite de tamanho
- nível de classe 1–150 e de job 1–70
- **o UID tem que ter formato de GUID** — sem essa checagem, toda leitura boa
  vinha acompanhada de um falso positivo com o GUID lido no lugar do nome
- o nome tem que repetir pra ser levado a sério (`Cacador`)

Na tela de seleção o roster inteiro passa uma vez cada (`Dipirono`,
`Novalgino`, `Tinhoso`...), então trocar de personagem custa mais confirmações
do que travar da primeira vez.

## Validação cruzada: level up × regra de três

Duas medições independentes do mesmo personagem (Corujo), sem nada lido da
memória:

| | classe | job |
|---|---|---|
| aprendido no level up | nível 17 = 34.392 | nível 12 = 11.436 |
| regra de três (% digitada) | nível 18 = 43.555 | nível 13 = 15.680 |
| razão entre níveis consecutivos | **1,266×** | 1,371× |

O crescimento medido entre os níveis 12 e 17 foi **1,246×**. A regra de três na
classe deu 1,266× — dois métodos que não compartilham nenhuma fonte, batendo
em 1,6%.

O job destoou (1,371×) porque a porcentagem foi lida da tela alguns minutos
antes da captura do XP. Dividir XP novo por porcentagem velha superestima o
tamanho do nível. **Consequência de projeto: o campo de porcentagem tem que
capturar o XP no instante em que o usuário digita, não depois.**

## A curva não extrapola — as duas tentativas, e como cada uma falha

Observado de verdade: o Galinho no nível 114 já apareceu com 18.720.722 XP
dentro do nível.

| ajuste | previsão pro 114 | erro |
|---|---|---|
| lei de potência `27,9 × n^2,37` (níveis 1–11) | 2.045.755 | 9× pra baixo |
| geométrica `1,246×` por nível (níveis 12–17) | 65 trilhões | 3,5 milhões× pra cima |

A curva cresce ~25% por nível no começo e **achata muito** depois. Cada ajuste
erra para um lado diferente, o que descarta qualquer fórmula simples: para
saber o nível 114 é preciso medir perto do 114.

Por isso aprender nível a nível não é contorno — é a única resposta correta.
