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
                sh "echo stage1"
            }
        }

        stage('stage2') {
            steps {
                sh "echo stage1"
            }
        }
    }
}
