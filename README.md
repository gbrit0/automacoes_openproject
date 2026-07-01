# Automações Openproject

Este projeto estabelece uma API para recebimento de webhooks (do OpenProject ou não) e executa ações na API Rest do OpenProject com fins de automatizar tarefas.

## Atribuição automática do Gestor ([Pacote de Trabalho #398](https://openproject.brggeradores.com.br/projects/melhorias-openproject/work_packages/398/activity))

Solicitação feita no projeto de melhorias do OpenProject para atribuição automática do gestor de cada equipe ao papel de responsável pelo pacote de trabalho.

A solução está baseada no uso de grupos em cada projeto, buscando o Administrador do Projeto considerando-o como Gestor da equipe e atribuindo seu id à relação de responsável.

* Endpoint /atribuicao_gestor

## Lançamento de Horas de Reunião

