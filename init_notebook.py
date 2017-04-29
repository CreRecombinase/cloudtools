#!/usr/bin/env python

import os
import json
from subprocess import call, Popen, PIPE

# get role of machine (master or worker)
role = Popen('/usr/share/google/get_metadata_value attributes/dataproc-role', shell=True, stdout=PIPE).communicate()[0]

# initialization actions to perform on master machine only
if role == 'Master':

    # download Anaconda Python 2.7 installation script
    call(['wget', '-P', '/home/anaconda2/', 'https://repo.continuum.io/archive/Anaconda2-4.3.1-Linux-x86_64.sh'])

    # install Anaconda in /home/anaconda2/
    call(['bash', '/home/anaconda2/Anaconda2-4.3.1-Linux-x86_64.sh', '-b', '-f', '-p', '/home/anaconda2/'])
    os.chmod('/home/anaconda2/', 0777)

    # additional packages to install
    pkgs = [
        'lxml',
        'jupyter-spark',
        'jgscm'
    ]

    # use pip to install packages
    for pkg in pkgs:
        call(['/home/anaconda2/bin/pip', 'install', pkg])

    # create Jupyter kernel spec file
    kernel = {
        'argv': [
            '/home/anaconda2/bin/python',
            '-m',
            'ipykernel',
            '-f',
            '{connection_file}'
        ],
        'display_name': 'Hail',
        'language': 'python',
        'env': {
            'PYTHONHASHSEED': '0',
            'SPARK_HOME': '/usr/lib/spark/',
            'PYTHONPATH': '/usr/lib/spark/python/:/usr/lib/spark/python/lib/py4j-0.10.3-src.zip:/home/hail/pyhail-hail-is-master-{}.zip'.format(hash)
        }
    }    

    # write kernel spec file to default Jupyter kernel directory
    os.makedirs('/home/anaconda2/share/jupyter/kernels/hail/')
    with open('/home/anaconda2/share/jupyter/kernels/hail/kernel.json', 'wb') as f:
        json.dump(kernel, f)

    # get latest Hail hash
    hash = Popen(['gsutil', 'cat', 'gs://hail-common/latest-hash.txt'], stdout=PIPE, stderr=PIPE).communicate()[0].strip()

    # Hail jar and zip names
    hail_jar = 'hail-hail-is-master-all-spark2.0.2-{}.jar'.format(hash)
    hail_zip = 'pyhail-hail-is-master-{}.zip'.format(hash)

    # make directory for Hail and Jupyter notebook related files
    os.mkdir('/home/hail/')
    os.chmod('/home/hail/', 0777)

    # copy Hail jar and zip to local directory on master node
    call(['gsutil', 'cp', 'gs://hail-common/{}'.format(hail_jar), '/home/hail/'])
    call(['gsutil', 'cp', 'gs://hail-common/{}'.format(hail_zip), '/home/hail/'])

    # modify default Spark config file to reference Hail jar and zip
    with open('/etc/spark/conf/spark-defaults.conf', 'ab') as f:
        opts = [
            'spark.files=/home/hail/{}'.format(hail_jar),
            'spark.submit.pyFiles=/home/hail/{}'.format(hail_zip),
            'spark.driver.extraClassPath=./{0}:/home/hail/{0}'.format(hail_jar),
            'spark.executor.extraClassPath=./{0}:/home/hail/{0}'.format(hail_jar)
        ]
        f.write('\n'.join(opts))

    # add Spark variable designating Anaconda Python executable as the default on driver
    with open('/etc/spark/conf/spark-env.sh', 'ab') as f:
        f.write('PYSPARK_DRIVER_PYTHON=/home/anaconda2/bin/python' + '\n')

    # create Jupyter configuration file
    call(['mkdir', '-p', '/home/anaconda2/etc/jupyter/'])
    with open('/home/anaconda2/etc/jupyter/jupyter_notebook_config.py', 'wb') as f:
	    opts = [
		    'c.Application.log_level = "DEBUG"',
		    'c.NotebookApp.ip = "127.0.0.1"',
		    'c.NotebookApp.open_browser = False',
		    'c.NotebookApp.port = 8123',
		    'c.NotebookApp.token = ""',
		    'c.NotebookApp.contents_manager_class = "jgscm.GoogleStorageContentManager"'
        ]
	    f.write('\n'.join(opts) + '\n')

    # setup jupyter-spark extension
    call(['/home/anaconda2/bin/jupyter', 'serverextension', 'enable', '--user', '--py', 'jupyter_spark'])
    call(['/home/anaconda2/bin/jupyter', 'nbextension', 'install', '--user', '--py', 'jupyter_spark'])
    call(['/home/anaconda2/bin/jupyter', 'nbextension', 'enable', '--user', '--py', 'jupyter_spark'])
    call(['/home/anaconda2/bin/jupyter', 'nbextension', 'enable', '--user', '--py', 'widgetsnbextension'])

    # create systemd service file for Jupyter notebook server process
    with open('/lib/systemd/system/jupyter.service', 'wb') as f:
    	opts = [
    		'[Unit]',
    		'Description=Jupyter Notebook',
    		'After=hadoop-yarn-resourcemanager.service',
    		'[Service]',
    		'Type=simple',
    		'User=root',
    		'Group=root',
    		'WorkingDirectory=/home/hail/',
            'ExecStart=/home/anaconda2/bin/python /home/anaconda2/bin/jupyter notebook',
    		'Restart=always',
    		'RestartSec=1',
    		'[Install]',
    		'WantedBy=multi-user.target'
    	]
    	f.write('\n'.join(opts) + '\n')

    # add Jupyter service to autorun and start it
    call(['systemctl', 'daemon-reload'])
    call(['systemctl', 'enable', 'jupyter'])
    call(['service', 'jupyter', 'start'])
