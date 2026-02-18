import { Component, OnInit, OnDestroy } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { RecipeService, Recipe } from './recipe.service';
import { AuthService, User } from './auth.service';
import { Subscription } from 'rxjs';
import { ScrapeTabComponent } from './scrape-tab/scrape-tab.component';
import { MyRecipesTabComponent } from './my-recipes-tab/my-recipes-tab.component';
import { MenuListTabComponent } from './menu-list-tab/menu-list-tab.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ScrapeTabComponent,
    MyRecipesTabComponent,
    MenuListTabComponent,
  ],
  templateUrl: './app.component.html',
  styleUrls: ['./app.component.scss'],
})
export class AppComponent implements OnInit, OnDestroy {
  title = 'Sous Chef';
  recipe: Recipe | null = null;
  steps: string[] = [];
  savedRecipes: Recipe[] = [];
  activeTab: 'scrape' | 'saved' | 'menu' = 'scrape';
  selectedRecipeIds = new Set<string>();
  menuRecipes: Recipe[] = [];

  currentUser: User | null = null;
  showLogin = false;
  showRegister = false;
  loginUsername = '';
  loginPassword = '';
  registerUsername = '';
  registerEmail = '';
  registerPassword = '';
  authError: string | null = null;
  authLoading = false;

  private subscriptions = new Subscription();

  constructor(
    private recipeService: RecipeService,
    private authService: AuthService
  ) {}

  ngOnInit(): void {
    const userSub = this.authService.currentUser$.subscribe((user) => {
      this.currentUser = user;
      if (user) {
        if (this.activeTab === 'saved') {
          this.loadSavedRecipes();
        }
      } else {
        this.savedRecipes = [];
        this.activeTab = 'scrape';
      }
    });
    this.subscriptions.add(userSub);
  }

  ngOnDestroy(): void {
    this.subscriptions.unsubscribe();
  }

  setActiveTab(tab: 'scrape' | 'saved' | 'menu'): void {
    this.activeTab = tab;
    if (tab === 'saved' && this.currentUser) {
      this.loadSavedRecipes();
    }
    if (tab === 'menu') {
      this.buildMenuRecipes();
    }
  }

  onRecipeLoaded(event: { recipe: Recipe; steps: string[] }): void {
    this.recipe = event.recipe;
    this.steps = event.steps;
  }

  onRecipeSaved(savedRecipe: Recipe): void {
    this.recipe = savedRecipe;
    this.loadSavedRecipes();
  }

  loadSavedRecipes(): void {
    if (!this.currentUser) return;
    this.recipeService.getRecipes().subscribe({
      next: (recipes) => (this.savedRecipes = recipes),
      error: (err) => console.error('Failed to load saved recipes:', err),
    });
  }

  onLoadRecipe(id: string): void {
    this.activeTab = 'scrape';
    this.recipeService.getRecipe(id).subscribe({
      next: (recipe) => {
        this.recipe = recipe;
        const instructions = recipe.instructions;
        this.steps = Array.isArray(instructions)
          ? instructions
          : instructions
          ? [instructions]
          : [];
        setTimeout(() => {
          document.querySelector('.recipe')?.scrollIntoView({ behavior: 'smooth' });
        }, 100);
      },
      error: (err) => {
        this.recipe = null;
        this.steps = [];
      },
    });
  }

  toggleRecipeSelection(recipeId: string): void {
    if (this.selectedRecipeIds.has(recipeId)) {
      this.selectedRecipeIds.delete(recipeId);
    } else {
      this.selectedRecipeIds.add(recipeId);
    }
    this.selectedRecipeIds = new Set(this.selectedRecipeIds);
  }

  createMenu(): void {
    if (this.selectedRecipeIds.size === 0) return;
    this.activeTab = 'menu';
    this.buildMenuRecipes();
  }

  buildMenuRecipes(): void {
    this.menuRecipes = this.savedRecipes.filter(
      (r) => r.id && this.selectedRecipeIds.has(r.id)
    );
  }

  onDeleteRecipe(id: string): void {
    if (!confirm('Are you sure you want to delete this recipe?')) return;
    this.recipeService.deleteRecipe(id).subscribe({
      next: () => {
        this.loadSavedRecipes();
        if (this.recipe?.id === id) {
          this.recipe = null;
          this.steps = [];
        }
      },
      error: (err) => console.error(err),
    });
  }

  onLogin(): void {
    this.authError = null;
    this.authLoading = true;
    this.authService.login(this.loginUsername, this.loginPassword).subscribe({
      next: () => {
        this.authLoading = false;
        this.showLogin = false;
        this.loginUsername = '';
        this.loginPassword = '';
      },
      error: (err) => {
        this.authLoading = false;
        this.authError = err?.error?.error || 'Login failed';
      },
    });
  }

  onRegister(): void {
    this.authError = null;
    this.authLoading = true;
    this.authService
      .register(this.registerUsername, this.registerPassword, this.registerEmail || undefined)
      .subscribe({
        next: () => {
          this.authLoading = false;
          this.showRegister = false;
          this.registerUsername = '';
          this.registerEmail = '';
          this.registerPassword = '';
        },
        error: (err) => {
          this.authLoading = false;
          this.authError = err?.error?.error || 'Registration failed';
        },
      });
  }

  onLogout(): void {
    this.authService.logout().subscribe({
      next: () => {
        this.recipe = null;
        this.savedRecipes = [];
        this.steps = [];
        this.selectedRecipeIds.clear();
        this.selectedRecipeIds = new Set();
        this.menuRecipes = [];
      },
      error: (err) => console.error('Logout error:', err),
    });
  }
}
