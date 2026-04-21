const bcrypt = require('bcrypt');
const ErrorCode = require('../controller/auth').ErrorCode;

class UserRepository {
    constructor() {
        this.users = [];
    }

    async getUser(username) {
        return this.users.find(user => user.username === username);
    }

    async createUser(username, password) {
        if (!username || !password) {
            throw { status: 400, message: "username and password are required", error_code: ErrorCode.INVALID_REQUEST };
        }
        if (password.length < 8) {
            throw { status: 422, message: "password is too short", error_code: ErrorCode.PASSWORD_TOO_SHORT };
        }

        const hashedPassword = await bcrypt.hash(password, 10);
        const newUser = {
            id: this.users.length + 1,
            username,
            password: hashedPassword,
            created_at: new Date().toISOString()
        };
        this.users.push(newUser);
        return { 
            id: newUser.id, 
            username: newUser.username, 
            status: "active", 
            created_at: newUser.created_at,
            error_code: ErrorCode.NO_ERROR,
            contract: "create-user",
            format: "json",
            status_code: 201
        };
    }
}

module.exports = new UserRepository();