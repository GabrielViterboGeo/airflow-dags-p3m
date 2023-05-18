from datetime import datetime
#Operatos padrão
from airflow.operators.python import PythonOperator
from airflow.operators.bash import BashOperator
#importando módulo do postgresoperator através do provider Postgres
from airflow.providers.postgres.operators.postgres import PostgresOperator
from airflow import DAG
#caminho relativo dos módulos .py
from p3m.includes.python.utils import create_get_dir
from p3m.includes.python.consumo import consumir_dado
from p3m.includes.python.logs import log_inativos,log_duplicados,log_geom
from p3m.includes.python.gravar_banco import gravar_banco
from p3m.includes.python.descompactar import descompactar as _descompactar
from p3m.includes.python.backup import make_backup
#Modulo para uso das variaveis registradas
from airflow.models import Variable

#Definição da DAG
etl_dag = DAG (
        'p3m_etl', 
        default_args = {
        "email":["gabrielviterbo.ti@fundeec.org.br"],#Alterar em produção
        "email_on_failure": False
        },
        start_date = datetime(2023, 5, 17),#Ajustar em produção
        schedule_interval = None, # '0 20 * * *',#Ajustar em produção
        catchup = False )

#Definição das tasks que compõem a dag
#Chama o .py importado como módulo referente a cada task

#Task que cria o diretorío automático do download caso necessário
#Variable.get('d_folder') variavel que tem valor da conexão do tipo file(path) para pasta de download dos arquivos
#Para implementação definir em Webserver admin>connections e admin>variables
criar_dir = PythonOperator (
    task_id = 'p3m_etl_criar_dir',
    python_callable = create_get_dir,
    op_args=[Variable.get('d_folder')],
    dag=etl_dag)

#Task que fazer o download e extrai os arquivos do zip na pasta da task anterior
#Variable.get('url_data') contém o endereço do serviço de acesso ao arquivo gdb
#Para implementação definir em Webserver admin>variables
consumo_dados = PythonOperator(
    task_id = 'p3m_etl_consumo_dados',
    python_callable = consumir_dado,
    op_args=[Variable.get('url_data'),Variable.get('d_folder')],#substituir as variáveis e o valores pelas criadas pelo usuário no UI
    dag=etl_dag)

# Task que extrai os arquivos do zip na pasta temporaria
descompactar = PythonOperator(
    task_id='p3m_etl_descompactar',
    python_callable=_descompactar,
    op_args=[Variable.get('d_folder')],
    dag=etl_dag
)

#Task que grava a base de dados no BD
#Bash_command é o caminho relativo .sh de execução
#gravar_dados = BashOperator(
#    task_id = 'gravar_dados',
#    bash_command="includes/bash/gravar_db.sh",
#    dag=etl_dag)

# ATUALIZADO: bash command transformado em Python
gravar_dados = PythonOperator(
    task_id = 'p3m_etl_gravar_dados',
    python_callable = gravar_banco,
    op_args=[Variable.get('d_folder')],
    dag=etl_dag)

#Task em python operator responsáveis por criar o log listando os processos com problemas para cada uma das situações de tratamento
inativos_log =PythonOperator(
    task_id='p3m_etl_inativos_log',
    python_callable=log_inativos,
    dag=etl_dag)

duplicados_log =PythonOperator(
    task_id='p3m_etl_duplicados_log',
    python_callable=log_duplicados,
    dag=etl_dag)

geom_log =PythonOperator(
    task_id='p3m_etl_geom_log',
    python_callable=log_geom,
    dag=etl_dag)

#Tasks que geram os logs e fazem tratamentos da base no BD
#Sql é o caminho relativo do .sql de execução
#postgres_conn_id é a conexão registrada no adm do webserver (admin>connections)
#Variable.get('p3m-conn') conexão do DB foi registrada como uma variável no adm do webserver (admin>variables) permitindo interoperabilidade
remover_inativos = PostgresOperator(
    task_id = 'p3m_etl_remover_inativos',
    postgres_conn_id = Variable.get('p3m_conn'),#Substituir pela variavel criada na UI e replicar nas demais tasks
    sql="sql/remov_inat.sql",
    dag=etl_dag)

remover_duplicados= PostgresOperator(
    task_id='p3m_etl_remover_duplicados',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql="sql/remov_dupli.sql",
    dag=etl_dag)

corrigir_geom = PostgresOperator(
    task_id='p3m_etl_corrigir_geom',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql= "sql/corrigir_geom.sql",
    dag=etl_dag)

vacuum = PostgresOperator(
    task_id='p3m_etl_vacuum_atl',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql= "sql/vacuum.sql",
    autocommit=True,
    dag=etl_dag)

atualizar_index = PostgresOperator(
    task_id='p3m_etl_reindex',
    postgres_conn_id= Variable.get('p3m_conn'),
    sql="sql/reindex.sql",
    dag=etl_dag)

atualizar_mvwcadastro=PostgresOperator(
    task_id='p3m_etl_atualizar_mvwcadastro',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql="sql/atualizar_mvwcadastro.sql",
    dag=etl_dag)

atualizar_mvwevt=PostgresOperator(
    task_id='p3m_etl_atualizar_mvwevt',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql="sql/atualizar_mvwevt.sql",
    dag=etl_dag)

atualizar_mvwpma=PostgresOperator(
    task_id='p3m_etl_atualizar_mvwpma',
    postgres_conn_id = Variable.get('p3m_conn'),
    sql="sql/atualizar_mvwpma.sql",
    dag=etl_dag)

#Task de construção da pasta de backup dos gdbs de cada run
mk_backup=PythonOperator(
    task_id='p3m_etl_backup',
    python_callable=make_backup,
    op_args=[ Variable.get('bkp_folder')],#Substituir pela variavel da pasta de backup criada na UI
    dag=etl_dag
)



criar_dir>>consumo_dados>>descompactar>>gravar_dados>>[inativos_log,duplicados_log,geom_log]>>remover_inativos>>remover_duplicados>>corrigir_geom>>vacuum>>atualizar_index>>[atualizar_mvwcadastro,atualizar_mvwevt,atualizar_mvwpma]>>mk_backup # type: ignore