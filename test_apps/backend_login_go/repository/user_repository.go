package repository

import (
	"backend_login_go/model"
	"database/sql"
	"errors"
)

type UserRepository interface {
	GetUser(username string) (*model.User, error)
}

type userRepositoryImpl struct {
	db *sql.DB
}

func NewUserRepository(db *sql.DB) UserRepository {
	return &userRepositoryImpl{db: db}
}

func (u *userRepositoryImpl) GetUser(username string) (*model.User, error) {
	var user model.User
	err := u.db.QueryRow("SELECT id, username, status, password, created_at FROM users WHERE username = $1", username).Scan(&user.ID, &user.Username, &user.Status, &user.Password, &user.CreatedAt)
	if err != nil {
		if err == sql.ErrNoRows {
			return nil, nil
		}
		return nil, errors.New("database error: " + err.Error())
	}
	return &user, nil
}