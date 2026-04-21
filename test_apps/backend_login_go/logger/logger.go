package logger

import (
	"log"
)

type Logger interface {
	LogInfo(message string, err error)
	LogError(message string, err error)
}

type logger struct{}

func NewLogger() Logger {
	return &logger{}
}

func (l *logger) LogInfo(message string, err error) {
	log.Printf("[INFO] %s", message)
}

func (l *logger) LogError(message string, err error) {
	if err != nil {
		log.Printf("[ERROR] %s: %v", message, err)
	} else {
		log.Printf("[ERROR] %s", message)
	}
}