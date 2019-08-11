pipeline {

    agent {

        docker {
            image 'maven:3-alpine'
        }
    }

    stages {
        stage('Checkout') {
            steps {
                cleanWs()
                checkout scm
            }
        }

        stage('stage1') {
            steps {
                sh "uname -a"
            }
        }

        stage('stage2') {
            steps {
                sh "uname -a" 
              
            }
        }
    }
}
