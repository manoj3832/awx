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
                echo "test1"
            }
        }

        stage('stage2') {
            steps {
                echo "test2" 
              
            }
        }
    }
}
