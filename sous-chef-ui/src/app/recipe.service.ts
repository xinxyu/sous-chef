import { Injectable } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';
import { environment } from '../environments/environment';

export interface Recipe {
  id?: string;
  title: string | null;
  total_time: number | null;
  yields: string | null;
  ingredients: string[];
  instructions: string[] | string;
  image: string | null;
  host: string | null;
  nutrients: any;
  source_url?: string;
  saved_at?: string;
}

@Injectable({
  providedIn: 'root',
})
export class RecipeService {
  private readonly apiUrl = environment.apiUrl;
  private readonly recipesUrl = `${this.apiUrl}/recipes`;

  constructor(private http: HttpClient) {}

  scrape(url: string): Observable<Recipe> {
    return this.http.post<Recipe>(`${this.apiUrl}/scrape`, { url }, { withCredentials: true });
  }

  saveRecipe(recipe: Recipe): Observable<Recipe> {
    return this.http.post<Recipe>(this.recipesUrl, recipe, { withCredentials: true });
  }

  getRecipes(): Observable<Recipe[]> {
    return this.http.get<Recipe[]>(this.recipesUrl, { withCredentials: true });
  }

  getRecipe(id: string): Observable<Recipe> {
    return this.http.get<Recipe>(`${this.recipesUrl}/${id}`, { withCredentials: true });
  }

  deleteRecipe(id: string): Observable<any> {
    return this.http.delete(`${this.recipesUrl}/${id}`, { withCredentials: true });
  }
}


