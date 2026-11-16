(() => {
  "use strict";

  const $ = (seletor) => document.querySelector(seletor);

  const el = {
    formulario: $("#formulario"),
    aviso: $("#aviso"),
    erroCarregamento: $("#erro-carregamento"),
    bairro: $("#bairro"),
    listaBairros: $("#lista-bairros"),
    texto: $("#texto"),
    botaoSugerir: $("#botao-sugerir"),
    sugestao: $("#sugestao"),
    grupoSituacao: $("#grupo-situacao"),
    opcoesSituacao: $("#opcoes-situacao"),
    perguntas: $("#perguntas"),
    grupoModalidade: $("#grupo-modalidade"),
    opcoesModalidade: $("#opcoes-modalidade"),
    botaoEnviar: $("#botao-enviar"),
    erroEnvio: $("#erro-envio"),
    resultado: $("#resultado"),
    resultadoConteudo: $("#resultado-conteudo"),
  };

  const MENSAGEM_ERRO_REDE =
    "Não foi possível conectar agora. Verifique sua internet e tente de novo. " +
    "Em caso de emergência, ligue 192 (SAMU).";

  let opcoes = null;
  let bairrosPorNome = new Map();
  let situacaoAtual = null;

  /* ---------- utilidades ---------- */

  function semAcento(texto) {
    return texto.normalize("NFD").replace(/\p{M}/gu, "").toLowerCase().trim();
  }

  function criar(tag, atributos = {}, texto = "") {
    const no = document.createElement(tag);
    for (const [nome, valor] of Object.entries(atributos)) {
      no.setAttribute(nome, valor);
    }
    if (texto) no.textContent = texto;
    return no;
  }

  async function requisitar(url, corpo) {
    const resposta = await fetch(url, {
      method: corpo ? "POST" : "GET",
      headers: corpo ? { "Content-Type": "application/json" } : undefined,
      body: corpo ? JSON.stringify(corpo) : undefined,
    });
    let dados = {};
    try {
      dados = await resposta.json();
    } catch (_) {
      /* resposta sem JSON: segue com objeto vazio */
    }
    if (!resposta.ok) {
      throw new Error(dados.erro || MENSAGEM_ERRO_REDE);
    }
    return dados;
  }

  function mostrarErro(campo, elementoErro, mensagem) {
    elementoErro.textContent = mensagem;
    elementoErro.hidden = false;
    campo.classList.add("campo-invalido");
  }

  function limparErros() {
    document.querySelectorAll(".erro").forEach((e) => {
      if (e.id === "erro-envio") return;
      e.hidden = true;
      e.textContent = "";
    });
    document
      .querySelectorAll(".campo-invalido")
      .forEach((c) => c.classList.remove("campo-invalido"));
    el.erroEnvio.hidden = true;
  }

  function limparResultado() {
    el.resultado.hidden = true;
    el.resultadoConteudo.replaceChildren();
  }

  function criarOpcaoRadio(nome, valor, texto) {
    const rotulo = criar("label", { class: "opcao" });
    const entrada = criar("input", { type: "radio", name: nome, value: valor });
    rotulo.append(entrada, criar("span", {}, texto));
    return rotulo;
  }

  /* ---------- carregamento ---------- */

  async function iniciar() {
    try {
      opcoes = await requisitar("/api/opcoes");
    } catch (_) {
      el.erroCarregamento.textContent =
        "Não foi possível carregar o formulário. Atualize a página. " +
        "Em caso de emergência, ligue 192 (SAMU).";
      el.erroCarregamento.hidden = false;
      el.botaoEnviar.disabled = true;
      return;
    }

    el.aviso.textContent = opcoes.aviso;

    const fragmento = document.createDocumentFragment();
    for (const nome of opcoes.bairros) {
      fragmento.append(criar("option", { value: nome }));
      bairrosPorNome.set(semAcento(nome), nome);
    }
    el.listaBairros.append(fragmento);

    for (const situacao of opcoes.situacoes) {
      el.opcoesSituacao.append(
        criarOpcaoRadio("situacao", situacao.id, situacao.titulo)
      );
    }
  }

  /* ---------- situação, perguntas e modalidade ---------- */

  function selecionarSituacao(id) {
    situacaoAtual = opcoes.situacoes.find((s) => s.id === id) || null;
    el.perguntas.replaceChildren();
    el.opcoesModalidade.replaceChildren();
    el.grupoModalidade.hidden = true;
    if (!situacaoAtual) return;

    for (const pergunta of situacaoAtual.perguntas) {
      const grupo = criar("fieldset", {
        class: "campo",
        "data-pergunta": pergunta.id,
        "aria-describedby": `erro-pergunta-${pergunta.id}`,
      });
      grupo.append(criar("legend", {}, pergunta.texto));
      const linha = criar("div", { class: "opcoes opcoes-linha" });
      linha.append(
        criarOpcaoRadio(`pergunta-${pergunta.id}`, "sim", "Sim"),
        criarOpcaoRadio(`pergunta-${pergunta.id}`, "nao", "Não")
      );
      grupo.append(
        linha,
        criar("p", { class: "erro", id: `erro-pergunta-${pergunta.id}`, hidden: "" })
      );
      el.perguntas.append(grupo);
    }

    if (situacaoAtual.modalidades.length) {
      for (const modalidade of situacaoAtual.modalidades) {
        el.opcoesModalidade.append(
          criarOpcaoRadio("modalidade", modalidade.id, modalidade.texto)
        );
      }
      el.grupoModalidade.hidden = false;
    }
  }

  el.opcoesSituacao.addEventListener("change", (evento) => {
    if (evento.target.name === "situacao") {
      selecionarSituacao(evento.target.value);
    }
  });

  /* ---------- sugestão a partir do texto livre ---------- */

  function mostrarSugestao(tipo, mensagem) {
    el.sugestao.className = `mensagem mensagem-${tipo}`;
    el.sugestao.textContent = mensagem;
    el.sugestao.hidden = false;
  }

  el.botaoSugerir.addEventListener("click", async () => {
    const texto = el.texto.value.trim();
    if (!texto) {
      mostrarSugestao("aviso", "Escreva o que você precisa no campo acima e toque de novo em “Sugerir uma opção”.");
      el.texto.focus();
      return;
    }

    el.botaoSugerir.disabled = true;
    try {
      const dados = await requisitar("/api/sugerir", { texto });
      const situacao = opcoes.situacoes.find((s) => s.id === dados.situacao);
      if (!situacao) {
        mostrarSugestao("aviso", "Não entendemos o que você escreveu. Escolha uma das opções abaixo.");
        return;
      }
      const radio = el.opcoesSituacao.querySelector(`input[value="${situacao.id}"]`);
      radio.checked = true;
      selecionarSituacao(situacao.id);
      limparResultado();
      mostrarSugestao("info", `Selecionamos “${situacao.titulo}”. Confira se é isso mesmo.`);
    } catch (erro) {
      mostrarSugestao("aviso", erro.message);
    } finally {
      el.botaoSugerir.disabled = false;
    }
  });

  /* ---------- envio ---------- */

  function validar() {
    limparErros();
    const invalidos = [];

    const bairro = bairrosPorNome.get(semAcento(el.bairro.value));
    if (!bairro) {
      mostrarErro(
        el.bairro.closest(".campo"),
        $("#erro-bairro"),
        "Escolha um bairro da lista. Comece a digitar para ver as opções."
      );
      invalidos.push(el.bairro);
    }

    if (!situacaoAtual) {
      mostrarErro(el.grupoSituacao, $("#erro-situacao"), "Escolha uma das opções.");
      invalidos.push(el.opcoesSituacao.querySelector("input"));
    }

    const marcadas = [];
    if (situacaoAtual) {
      for (const pergunta of situacaoAtual.perguntas) {
        const grupo = el.perguntas.querySelector(`[data-pergunta="${pergunta.id}"]`);
        const escolhida = grupo.querySelector("input:checked");
        if (!escolhida) {
          mostrarErro(grupo, $(`#erro-pergunta-${pergunta.id}`), "Responda sim ou não.");
          invalidos.push(grupo.querySelector("input"));
        } else if (escolhida.value === "sim") {
          marcadas.push(pergunta.id);
        }
      }
    }

    let modalidade = null;
    if (situacaoAtual && situacaoAtual.modalidades.length) {
      const escolhida = el.opcoesModalidade.querySelector("input:checked");
      if (!escolhida) {
        mostrarErro(el.grupoModalidade, $("#erro-modalidade"), "Escolha o tipo de atendimento.");
        invalidos.push(el.opcoesModalidade.querySelector("input"));
      } else {
        modalidade = escolhida.value;
      }
    }

    if (invalidos.length) {
      invalidos[0].focus();
      return null;
    }
    return { bairro, situacao: situacaoAtual.id, marcadas, modalidade };
  }

  el.formulario.addEventListener("submit", async (evento) => {
    evento.preventDefault();
    if (!opcoes) return;

    const dados = validar();
    if (!dados) return;

    const textoBotao = el.botaoEnviar.textContent;
    el.botaoEnviar.disabled = true;
    el.botaoEnviar.textContent = "Buscando orientação…";
    limparResultado();

    try {
      const resposta = await requisitar("/api/orientar", dados);
      mostrarResultado(resposta.orientacao);
    } catch (erro) {
      el.erroEnvio.textContent = erro.message;
      el.erroEnvio.hidden = false;
    } finally {
      el.botaoEnviar.disabled = false;
      el.botaoEnviar.textContent = textoBotao;
    }
  });

  el.formulario.addEventListener("input", () => {
    if (!el.resultado.hidden) limparResultado();
  });

  /* ---------- resultado ---------- */

  /* O motor devolve um subconjunto simples de Markdown: negrito, itálico,
     listas de unidades ("- ") e parágrafos. Este conversor trata só isso e
     escapa qualquer HTML antes de montar a página. */

  function escapar(texto) {
    return texto
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function emLinha(texto) {
    return escapar(texto)
      .replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>")
      .replace(/\*(.+?)\*/g, "<em>$1</em>")
      .replace(
        /https?:\/\/[^\s<]+/g,
        (url) => `<a href="${url}" target="_blank" rel="noopener noreferrer">${url}</a>`
      );
  }

  function linhaDeUnidade(linha) {
    const telefone = linha.match(/^Tel:\s*(.+)$/);
    if (telefone) {
      const numero = telefone[1].trim();
      const digitos = numero.replace(/\D/g, "");
      if (/^[\d\s()+.\-]+$/.test(numero) && digitos.length >= 8 && digitos.length <= 13) {
        return `Tel: <a href="tel:${digitos}">${escapar(numero)}</a>`;
      }
    }
    return emLinha(linha);
  }

  function converterOrientacao(markdown, aviso) {
    const blocos = markdown.split(/\n{2,}/).map((b) => b.trim()).filter(Boolean);
    const saida = [];
    let lista = null;

    const fecharLista = () => {
      if (lista) {
        saida.push(`<ul class="unidades">${lista.join("")}</ul>`);
        lista = null;
      }
    };

    blocos.forEach((bloco, indice) => {
      if (bloco.startsWith("- ")) {
        const [nome, ...resto] = bloco.slice(2).split("\n").map((l) => l.trim()).filter(Boolean);
        const linhas = [`<p class="unidade-nome">${emLinha(nome)}</p>`];
        resto.forEach((linha) => linhas.push(`<p>${linhaDeUnidade(linha)}</p>`));
        (lista ||= []).push(`<li>${linhas.join("")}</li>`);
        return;
      }

      fecharLista();
      const html = emLinha(bloco).replace(/\n/g, "<br>");
      if (indice === 0) {
        saida.push(`<p class="destaque">${html}</p>`);
      } else if (/^\*\*[^*]+:\*\*$/.test(bloco)) {
        saida.push(`<h3>${html}</h3>`);
      } else if (bloco === aviso || /^\*[^*].*\*$/s.test(bloco)) {
        saida.push(`<p class="nota">${html}</p>`);
      } else {
        saida.push(`<p>${html}</p>`);
      }
    });

    fecharLista();
    return saida.join("");
  }

  function mostrarResultado(markdown) {
    el.resultadoConteudo.innerHTML = converterOrientacao(markdown, opcoes.aviso);
    el.resultado.hidden = false;
    const reduzMovimento = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.resultado.scrollIntoView({ behavior: reduzMovimento ? "auto" : "smooth", block: "start" });
    el.resultado.focus({ preventScroll: true });
  }

  iniciar();
})();
