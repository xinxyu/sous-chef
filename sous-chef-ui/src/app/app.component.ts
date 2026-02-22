import { Component, effect, signal, OnInit } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';
import { AuthService, User } from './auth.service';
import { ScrapeTabComponent } from './scrape-tab/scrape-tab.component';
import { MyRecipesTabComponent } from './my-recipes-tab/my-recipes-tab.component';
import { MenuListTabComponent } from './menu-list-tab/menu-list-tab.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    FormsModule,
    ScrapeTabComponent,
    MyRecipesTabComponent,
    MenuListTabComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit {
  readonly title = 'Sous Chef';

  readonly recipe = signal<Recipe | null>(null);
  readonly steps = signal<string[]>([]);
  readonly savedRecipes = signal<Recipe[]>([]);
  readonly activeTab = signal<'scrape' | 'saved' | 'menu'>('scrape');
  readonly selectedRecipeIds = signal<Set<string>>(new Set());
  readonly menuRecipes = signal<Recipe[]>([]);

  readonly showLogin = signal(false);
  readonly showRegister = signal(false);
  readonly showForgotPassword = signal(false);
  readonly showResetPassword = signal(false);
  readonly showVerifyEmailResult = signal<'success' | 'error' | null>(null);
  readonly verifyEmailMessage = signal<string>('');
  readonly authError = signal<string | null>(null);
  readonly authSuccess = signal<string | null>(null);
  readonly authLoading = signal(false);

  loginUsername = '';
  loginPassword = '';
  registerUsername = '';
  registerEmail = '';
  registerPassword = '';
  forgotEmail = '';
  resetPasswordToken = '';
  resetNewPassword = '';
  resetConfirmPassword = '';

  constructor(
    private recipeService: RecipeService,
    public authService: AuthService
  ) {
    effect(() => {
      const user = this.authService.currentUser();
      if (!user) {
        this.savedRecipes.set([]);
        this.activeTab.set('scrape');
      }
    });
    effect(() => {
      const user = this.authService.currentUser();
      const tab = this.activeTab();
      if (user && tab === 'saved') {
        this.loadSavedRecipes();
      }
    });
  }

  ngOnInit(): void {
    if (typeof window === 'undefined') return;
    const pathname = window.location.pathname || '';
    const params = new URLSearchParams(window.location.search);
    const token = params.get('token');
    if (!token) return;
    const cleanUrl = (): void => window.history.replaceState({}, '', '/');

    if (pathname.includes('verify-email')) {
      cleanUrl();
      this.authService.verifyEmail(token).subscribe({
        next: (res) => {
          this.verifyEmailMessage.set(res.message || 'Email verified. You can now log in.');
          this.showVerifyEmailResult.set('success');
        },
        error: (err) => {
          this.verifyEmailMessage.set(err?.error?.error || 'Invalid or expired verification link.');
          this.showVerifyEmailResult.set('error');
        },
      });
    } else if (pathname.includes('reset-password')) {
      this.resetPasswordToken = token;
      this.showResetPassword.set(true);
      cleanUrl();
    } else {
      this.resetPasswordToken = token;
      this.showResetPassword.set(true);
      cleanUrl();
    }
  }

  closeVerifyEmailResult(): void {
    this.showVerifyEmailResult.set(null);
    this.verifyEmailMessage.set('');
    this.showLogin.set(true);
  }

  closeRegister(): void {
    this.showRegister.set(false);
    this.authSuccess.set(null);
  }

  setActiveTab(tab: 'scrape' | 'saved' | 'menu'): void {
    this.activeTab.set(tab);
    const user = this.authService.currentUser();
    if (tab === 'saved' && user) {
      this.loadSavedRecipes();
    }
    if (tab === 'menu') {
      this.buildMenuRecipes();
    }
  }

  onRecipeLoaded(event: { recipe: Recipe; steps: string[] }): void {
    this.recipe.set(event.recipe);
    this.steps.set(event.steps);
  }

  onRecipeSaved(savedRecipe: Recipe): void {
    this.recipe.set(savedRecipe);
    this.loadSavedRecipes();
  }

  loadSavedRecipes(): void {
    const user = this.authService.currentUser();
    if (!user) return;
    this.recipeService.getRecipes().subscribe({
      next: (recipes) => this.savedRecipes.set(recipes),
      error: (err) => console.error('Failed to load saved recipes:', err),
    });
  }

  onLoadRecipe(id: string): void {
    this.activeTab.set('scrape');
    this.recipeService.getRecipe(id).subscribe({
      next: (recipe) => {
        this.recipe.set(recipe);
        const instructions = recipe.instructions;
        const steps = Array.isArray(instructions)
          ? instructions
          : instructions
            ? [instructions]
            : [];
        this.steps.set(steps);
        setTimeout(() => {
          document.querySelector('.recipe')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      },
      error: () => {
        this.recipe.set(null);
        this.steps.set([]);
      },
    });
  }

  toggleRecipeSelection(recipeId: string): void {
    this.selectedRecipeIds.update((ids) => {
      const next = new Set(ids);
      if (next.has(recipeId)) next.delete(recipeId);
      else next.add(recipeId);
      return next;
    });
  }

  createMenu(): void {
    if (this.selectedRecipeIds().size === 0) return;
    this.activeTab.set('menu');
    this.buildMenuRecipes();
  }

  buildMenuRecipes(): void {
    const saved = this.savedRecipes();
    const ids = this.selectedRecipeIds();
    this.menuRecipes.set(saved.filter((r) => r.id != null && ids.has(r.id)));
  }

  onDeleteRecipe(id: string): void {
    if (!confirm('Are you sure you want to delete this recipe?')) return;
    this.recipeService.deleteRecipe(id).subscribe({
      next: () => {
        this.loadSavedRecipes();
        if (this.recipe()?.id === id) {
          this.recipe.set(null);
          this.steps.set([]);
        }
      },
      error: (err) => console.error(err),
    });
  }

  onLogin(): void {
    this.authError.set(null);
    this.authLoading.set(true);
    this.authService.login(this.loginUsername, this.loginPassword).subscribe({
      next: () => {
        this.authLoading.set(false);
        this.showLogin.set(false);
        this.loginUsername = '';
        this.loginPassword = '';
      },
      error: (err) => {
        this.authLoading.set(false);
        this.authError.set(err?.error?.error || 'Login failed');
      },
    });
  }

  onRegister(): void {
    this.authError.set(null);
    this.authSuccess.set(null);
    this.authLoading.set(true);
    this.authService
      .register(this.registerUsername, this.registerPassword, this.registerEmail || undefined)
      .subscribe({
        next: (res: { message?: string; user?: User }) => {
          this.authLoading.set(false);
          if (res.user) {
            this.showRegister.set(false);
            this.registerUsername = '';
            this.registerEmail = '';
            this.registerPassword = '';
          } else {
            const email = this.registerEmail;
            this.authSuccess.set(
              `We've sent a verification link to ${email}. Please check your inbox to verify your account.`
            );
            this.registerUsername = '';
            this.registerEmail = '';
            this.registerPassword = '';
          }
        },
        error: (err) => {
          this.authLoading.set(false);
          this.authError.set(err?.error?.error || 'Registration failed');
        },
      });
  }

  onForgotPassword(): void {
    this.authError.set(null);
    this.authSuccess.set(null);
    if (!this.forgotEmail.trim()) {
      this.authError.set('Please enter your email.');
      return;
    }
    this.authLoading.set(true);
    this.authService.forgotPassword(this.forgotEmail.trim()).subscribe({
      next: (res) => {
        this.authLoading.set(false);
        this.authSuccess.set(res.message || 'If an account exists with this email, you will receive a reset link.');
      },
      error: (err) => {
        this.authLoading.set(false);
        this.authError.set(err?.error?.error || 'Request failed');
      },
    });
  }

  onResetPassword(): void {
    this.authError.set(null);
    this.authSuccess.set(null);
    if (!this.resetNewPassword || this.resetNewPassword.length < 6) {
      this.authError.set('Password must be at least 6 characters.');
      return;
    }
    if (this.resetNewPassword !== this.resetConfirmPassword) {
      this.authError.set('Passwords do not match.');
      return;
    }
    const token = this.resetPasswordToken || new URLSearchParams(window.location.search).get('token');
    if (!token) {
      this.authError.set('Invalid or missing reset link.');
      return;
    }
    this.authLoading.set(true);
    this.authService.resetPassword(token, this.resetNewPassword).subscribe({
      next: (res) => {
        this.authLoading.set(false);
        this.authSuccess.set(res.message || 'Password updated. You can now log in.');
        this.resetPasswordToken = '';
        this.resetNewPassword = '';
        this.resetConfirmPassword = '';
        setTimeout(() => {
          this.showResetPassword.set(false);
          this.showLogin.set(true);
          this.authSuccess.set(null);
        }, 2500);
      },
      error: (err) => {
        this.authLoading.set(false);
        this.authError.set(err?.error?.error || 'Failed to reset password');
      },
    });
  }

  openForgotPassword(): void {
    this.authError.set(null);
    this.authSuccess.set(null);
    this.showLogin.set(false);
    this.showForgotPassword.set(true);
  }

  closeForgotPassword(): void {
    this.authError.set(null);
    this.authSuccess.set(null);
    this.showForgotPassword.set(false);
    this.showLogin.set(true);
  }

  onLogout(): void {
    this.authService.logout().subscribe({
      next: () => {
        this.recipe.set(null);
        this.savedRecipes.set([]);
        this.steps.set([]);
        this.selectedRecipeIds.set(new Set());
        this.menuRecipes.set([]);
      },
      error: (err) => console.error('Logout error:', err),
    });
  }
}
